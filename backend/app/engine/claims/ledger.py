"""The Claim Ledger: detect claims, retrieve approved facts, verify, decide a verdict.

Pipeline per claim (each step is recorded so the UI can show "How this verdict was reached"):
  1. detect   - pattern rules (+ optional LLM extraction), unioned
  2. retrieve - hybrid dense + BM25 over current facts, plus a separate superseded pool
  3. verify   - local NLI (fact => claim) and exact numeric comparison; a numeric mismatch on
                the same topic is a contradiction regardless of the NLI model
  4. quote    - a supported verdict must cite a verbatim span of the fact
  5. decide   - supported / outdated / contradicted / unsupported / needs_review

The LLM never decides truth: it can only propose claims and wording.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.engine.checkers.base import make_finding
from app.engine.claims.detect import ClaimCandidate, PatternHit, detect_claims, union
from app.engine.claims.quantities import Quantity, compare, extract
from app.engine.claims.quote import best_quote, quote_is_verbatim
from app.engine.claims.retrieve import Candidate, Retriever, tokens
from app.engine.context import FactInfo, ReviewContext
from app.engine.schema import Evidence, Finding, NliLabel, NormalisedDoc, Span
from app.engine.text import compact
from app.ml.embeddings import Embedder
from app.ml.nli import NliModel, NliScores

Verdict = Literal["supported", "outdated", "contradicted", "unsupported", "needs_review"]

ENTAIL_SUPPORTED = 0.7
CONTRADICT = 0.6
AMBIGUOUS = (0.4, 0.6)
MIN_DENSE_RELEVANCE = 0.55
MIN_DENSE_CONTRADICT = 0.75
MIN_DENSE_EVIDENCE = 0.7
# Calibrated on data/eval: true numeric contradictions all had similarity >= 0.746,
# numbers compared against loosely related facts sat at 0.68-0.73.
MIN_DENSE_NUMERIC = 0.74
MIN_DENSE_LEXICAL = 0.75
MIN_LEXICAL_COVERAGE = 0.6
LEXICAL_SUPPORT_CONFIDENCE = 0.75

ClaimExtractor = Callable[[NormalisedDoc, ReviewContext], Awaitable[list[ClaimCandidate]]]


class ClaimRecord(BaseModel):
    block: int
    span: Span
    text: str
    hypothesis: str
    claim_type: str
    verdict: Verdict
    fact_id: str | None = None
    current_fact_id: str | None = None
    quote: str | None = None
    scores: dict[str, float | str | None] = Field(default_factory=dict)
    confidence: float
    steps: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    source: str = "rules"


@dataclass
class _Scored:
    candidate: Candidate
    nli: NliScores
    numeric: str
    claim_q: Quantity | None
    fact_q: Quantity | None
    relevant: bool

    @property
    def fact(self) -> FactInfo:
        return self.candidate.fact

    @property
    def entail(self) -> float:
        return 0.02 if self.numeric == "mismatch" else self.nli["entailment"]

    @property
    def contradict(self) -> float:
        return max(self.nli["contradiction"], 0.95 if self.numeric == "mismatch" else 0.0)

    @property
    def label(self) -> NliLabel:
        best = max(
            ("entailment", self.entail),
            ("contradiction", self.contradict),
            ("neutral", self.nli["neutral"]),
            key=lambda kv: kv[1],
        )
        return best[0]  # type: ignore[return-value]


def _lexical_nli(fact: str, claim: str) -> NliScores:
    """Fallback when the NLI model is unavailable: overlap-based, deliberately cautious."""
    claim_tokens = set(tokens(claim))
    overlap = len(claim_tokens & set(tokens(fact))) / max(1, len(claim_tokens))
    entail = min(0.65, overlap * 0.75)
    return {"entailment": entail, "contradiction": 0.05, "neutral": 1 - entail - 0.05}


def _numeric_text(claim: ClaimCandidate) -> str:
    """Clause text with rule-pattern phrases blanked out (same length, so offsets hold).
    "100% secure" is an absolute claim for CLM-04, not a percentage to compare."""
    text = list(claim.span.text)
    for hit in claim.hits:
        for i in range(hit.span.start - claim.span.start, hit.span.end - claim.span.start):
            if 0 <= i < len(text):
                text[i] = " "
    return "".join(text)


def _topicality(s: "_Scored") -> float:
    """How on-topic a fact is: dense similarity when available, else its fused rank score."""
    return s.candidate.dense if s.candidate.dense is not None else s.candidate.rrf


def _lexically_supported(claim: ClaimCandidate, s: "_Scored") -> bool:
    """Deterministic support when small NLI models are too strict about extra detail:
    the fact is on-topic, nothing contradicts, a verbatim quote exists, and either the
    numbers agree exactly or the quote covers most of the claim's content words."""
    if not s.relevant or s.numeric == "mismatch" or s.contradict >= 0.2:
        return False
    if s.candidate.dense is not None and s.candidate.dense < MIN_DENSE_LEXICAL:
        return False
    quote = best_quote(claim.hypothesis, s.fact.statement)
    if not quote:
        return False
    claim_words = set(tokens(_numeric_text(claim)))
    coverage = len(claim_words & set(tokens(s.fact.statement))) / max(1, len(claim_words))
    return s.numeric == "match" or coverage >= MIN_LEXICAL_COVERAGE


def _relevant(claim: str, candidate: Candidate) -> bool:
    shared = {
        t for t in set(tokens(claim)) & set(tokens(candidate.fact.statement)) if not t.isdigit()
    }
    if not shared:
        return False
    return candidate.dense is None or candidate.dense >= MIN_DENSE_RELEVANCE


class ClaimLedger:
    name = "claims"
    label = "Claim Ledger"

    def __init__(
        self,
        nli: NliModel | None,
        embedder: Embedder | None,
        extractor: ClaimExtractor | None = None,
    ) -> None:
        self.nli = nli
        self.embedder = embedder
        self.extractor = extractor
        self.records: list[ClaimRecord] = []
        self._retriever: Retriever | None = None

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        candidates = detect_claims(doc, ctx)
        if self.extractor is not None:
            candidates = union(candidates, await self.extractor(doc, ctx))
        retriever = Retriever(ctx, self.embedder)
        retrieved = [retriever.retrieve(c.hypothesis) for c in candidates]
        pairs = [
            (cand.fact.statement, claim.hypothesis)
            for claim, (current, old) in zip(candidates, retrieved, strict=True)
            for cand in (*current, *old)
        ]
        if self.nli is not None:
            scores = self.nli.predict(pairs)
        else:
            scores = [_lexical_nli(fact, claim) for fact, claim in pairs]

        self._retriever = retriever
        has_offer_disclaimer = "t&capply" in compact(doc.text)
        findings: list[Finding] = []
        cursor = 0
        self.records = []
        for claim, (current, old) in zip(candidates, retrieved, strict=True):
            n = len(current) + len(old)
            claim_scores = scores[cursor : cursor + n]
            cursor += n
            scored = [
                self._score(claim, cand, s)
                for cand, s in zip((*current, *old), claim_scores, strict=True)
            ]
            record = self._decide(claim, scored[: len(current)], scored[len(current) :], ctx)
            self.records.append(record)
            findings += self._findings(claim, record, scored, ctx, has_offer_disclaimer)
        return findings

    @staticmethod
    def _score(claim: ClaimCandidate, cand: Candidate, nli: NliScores) -> _Scored:
        relevant = _relevant(claim.hypothesis, cand)
        numeric, cq, fq = compare(_numeric_text(claim), cand.fact.statement)
        if not relevant and numeric == "mismatch":
            numeric = "na"  # different topic: the numbers are not comparable
        return _Scored(cand, nli, numeric, cq, fq, relevant)

    def _decide(
        self,
        claim: ClaimCandidate,
        current: list[_Scored],
        old: list[_Scored],
        ctx: ReviewContext,
    ) -> ClaimRecord:
        steps = [f'Detected {claim.claim_type} claim via {claim.source}: "{claim.span.text}"']
        if current:
            steps.append(
                "Retrieved current facts (dense + BM25, RRF): "
                + ", ".join(s.fact.id for s in current)
            )
        if old:
            steps.append("Retrieved superseded facts: " + ", ".join(s.fact.id for s in old))
        verifier = self.nli.name if self.nli else "lexical fallback (NLI model unavailable)"
        steps.append(f"Verified each pair with {verifier} and exact numeric comparison")

        def record(
            verdict: Verdict,
            best: _Scored | None,
            confidence: float,
            quote: str | None = None,
            current_fact_id: str | None = None,
        ) -> ClaimRecord:
            scores: dict[str, float | str | None] = {}
            if best is not None:
                scores = {
                    "entailment": round(best.entail, 3),
                    "contradiction": round(best.contradict, 3),
                    "neutral": round(best.nli["neutral"], 3),
                    "dense": round(best.candidate.dense, 3) if best.candidate.dense else None,
                    "bm25": round(best.candidate.bm25, 3),
                    "numeric": best.numeric,
                }
            return ClaimRecord(
                block=claim.block,
                span=Span(block=claim.block, start=claim.span.start, end=claim.span.end),
                text=claim.span.text,
                hypothesis=claim.hypothesis,
                claim_type=claim.claim_type,
                verdict=verdict,
                fact_id=best.fact.id if best else None,
                scores=scores,
                confidence=round(confidence, 3),
                steps=steps,
                rule_hits=[h.rule_code for h in claim.hits],
                source=claim.source,
                quote=quote,
                current_fact_id=current_fact_id,
            )

        best_entail = max(current, key=lambda s: s.entail, default=None)
        if best_entail and best_entail.entail >= ENTAIL_SUPPORTED:
            quote = best_quote(claim.hypothesis, best_entail.fact.statement)
            if quote and quote_is_verbatim(quote, best_entail.fact.statement):
                steps.append(
                    f'Quote check passed: "{quote}" appears verbatim in {best_entail.fact.id}'
                )
                steps.append(f"Verdict: supported (entailment {best_entail.entail:.2f} >= 0.70)")
                return record("supported", best_entail, best_entail.entail, quote=quote)
            steps.append("Quote check failed: no verbatim span of the fact supports the claim")
            steps.append("Verdict downgraded to needs_review")
            return record("needs_review", best_entail, 0.5)

        lexical = [s for s in current if _lexically_supported(claim, s)]
        if lexical:
            best = max(lexical, key=lambda s: (s.numeric == "match", s.candidate.dense or 0))
            quote = best_quote(claim.hypothesis, best.fact.statement)
            steps.append(
                f'NLI was inconclusive ({best.entail:.2f}), but {best.fact.id} agrees exactly '
                f'{"on the numbers" if best.numeric == "match" else "in wording"} and the claim '
                f'quotes it verbatim: "{quote}"'
            )
            steps.append("Verdict: supported (deterministic agreement, lower confidence)")
            return record("supported", best, LEXICAL_SUPPORT_CONFIDENCE, quote=quote)

        for stale in sorted(old, key=lambda s: -s.entail):
            successor = ctx.facts.get(stale.fact.superseded_by or "")
            matches_old = stale.relevant and (stale.numeric == "match" or stale.entail >= 0.5)
            if not (matches_old and successor and successor.current):
                continue
            differs = compare(_numeric_text(claim), successor.statement)[0] != "match"
            if differs:
                confidence = max(stale.entail, 0.9 if stale.numeric == "match" else 0.0)
                steps.append(
                    f"Matches superseded fact {stale.fact.id}; current fact {successor.id} "
                    f'says: "{successor.statement}"'
                )
                steps.append("Verdict: outdated")
                return record(
                    "outdated",
                    stale,
                    confidence,
                    current_fact_id=successor.id,
                    quote=best_quote(claim.hypothesis, stale.fact.statement),
                )

        # A numeric mismatch counts unless a more on-topic fact agrees on the number
        # (e.g. "zero MDR on UPI" should not be contradicted by the net-banking fee).
        agreeing = [_topicality(s) for s in current if s.relevant and s.numeric == "match"]
        best_agreeing = max(agreeing, default=-1.0)
        contra = [
            s
            for s in current
            if s.relevant
            and s.contradict >= CONTRADICT
            and (
                (
                    s.numeric == "mismatch"
                    and _topicality(s) > best_agreeing
                    and (s.candidate.dense is None or s.candidate.dense >= MIN_DENSE_NUMERIC)
                )
                # NLI alone may only contradict a clearly on-topic fact, and never a claim that
                # is just a risky phrase (those are handled by their own rule).
                or (
                    s.numeric != "mismatch"
                    and not claim.hits
                    and (s.candidate.dense is None or s.candidate.dense >= MIN_DENSE_CONTRADICT)
                )
            )
        ]
        if contra:
            best = max(contra, key=lambda s: (s.numeric == "mismatch", _topicality(s)))
            reason = (
                f"numbers differ ({best.claim_q.span.text if best.claim_q else '?'} vs "
                f"{best.fact_q.span.text if best.fact_q else '?'})"
                if best.numeric == "mismatch"
                else f"contradiction {best.contradict:.2f} >= 0.60"
            )
            steps.append(f"Verdict: contradicted by {best.fact.id}: {reason}")
            return record("contradicted", best, best.contradict, current_fact_id=best.fact.id)

        pool = [s for s in current if s.relevant] or current
        top = max(pool, key=lambda s: max(s.entail, s.contradict), default=None)
        top_score = max(top.entail, top.contradict) if top else 0.0
        # A risky phrase (superlative, absolute, guarantee) that no fact entails is unsupported,
        # never "ambiguous": the rule exists precisely because such claims need proof.
        if top and AMBIGUOUS[0] <= top_score < AMBIGUOUS[1] and top.relevant and not claim.hits:
            steps.append(f"Best score {top_score:.2f} is ambiguous (0.40-0.60): a person decides")
            return record("needs_review", top, 0.5)
        steps.append("No approved fact supports this claim. Verdict: unsupported")
        return record("unsupported", top, 1 - (top.entail if top else 0.0))

    def _findings(
        self,
        claim: ClaimCandidate,
        record: ClaimRecord,
        scored: list[_Scored],
        ctx: ReviewContext,
        has_offer_disclaimer: bool,
    ) -> list[Finding]:
        findings: list[Finding] = []
        evidence = _evidence(record, scored)
        for hit in claim.hits:
            hit_evidence = self._hit_evidence(hit, claim) or evidence
            finding = self._pattern_finding(
                hit, claim, record, ctx, hit_evidence, has_offer_disclaimer
            )
            if finding:
                findings.append(finding)

        if record.verdict == "outdated" and record.current_fact_id:
            findings.append(self._outdated_finding(claim, record, scored, ctx, evidence))
        elif record.verdict == "contradicted":
            findings.append(self._contradicted_finding(claim, record, scored, ctx, evidence))
        elif record.verdict in ("unsupported", "needs_review") and not claim.hits:
            rule = ctx.rules["CLM-05"]
            needs_review = record.verdict == "needs_review"
            findings.append(
                make_finding(
                    rule,
                    type="unsupported_claim",
                    block=claim.block,
                    start=claim.span.start,
                    end=claim.span.end,
                    text=claim.span.text,
                    explanation=(
                        "Preflight could not confirm or rule out this claim against the approved "
                        "facts, so a reviewer should check it."
                        if needs_review
                        else "No approved fact backs this claim. Add a source to the "
                        f"approved-facts registry or remove it ({rule.code}, {rule.source_ref})."
                    ),
                    # A vague claim with no number is a judgement call, so a person looks first.
                    confidence=0.5
                    if needs_review
                    else min(0.85, record.confidence)
                    if claim.claim_type == "numeric"
                    else 0.55,
                    detector="nli",
                    evidence=evidence,
                )
            )
        return findings

    def _hit_evidence(self, hit: PatternHit, claim: ClaimCandidate) -> list[Evidence]:
        """The approved fact closest to one risky phrase ("100% secure" -> the encryption
        fact), so the author sees what the brand *can* say instead."""
        others = [h for h in claim.hits if h is not hit]
        query = _numeric_text(
            ClaimCandidate(claim.block, claim.span, claim.hypothesis, claim.claim_type, others)
        )
        if self._retriever is None:
            return []
        current, _ = self._retriever.retrieve(query)
        if not current:
            return []
        top = current[0]
        if top.dense is not None and top.dense < MIN_DENSE_EVIDENCE:
            return []
        hypothesis = query.strip()
        nli = (
            self.nli.predict([(top.fact.statement, hypothesis)])[0]
            if self.nli
            else _lexical_nli(top.fact.statement, hypothesis)
        )
        label = max(nli, key=lambda k: nli[k])
        quote = best_quote(hypothesis, top.fact.statement) or top.fact.statement.rstrip(".")
        return [
            Evidence.model_validate(
                {
                    "fact_id": top.fact.id,
                    "quote": quote,
                    "nli": label,
                    "score": round(nli[label], 3),
                }
            )
        ]

    @staticmethod
    def _pattern_finding(
        hit: PatternHit,
        claim: ClaimCandidate,
        record: ClaimRecord,
        ctx: ReviewContext,
        evidence: list[Evidence],
        has_offer_disclaimer: bool,
    ) -> Finding | None:
        rule = ctx.rules[hit.rule_code]
        supported = record.verdict == "supported"
        if hit.rule_code == "CLM-01" and supported:
            return None
        if hit.rule_code == "CLM-08" and (supported or has_offer_disclaimer):
            return None
        reasons = {
            "CLM-01": f'"{hit.span.text}" is a superlative that no approved fact backs.',
            "CLM-04": f'"{hit.span.text}" is an absolute security or safety claim. No product '
            "can promise this; describe the specific protection instead.",
            "CLM-06": f'"{hit.span.text}" promises an outcome the brand cannot guarantee.',
            "CLM-08": f'"{hit.span.text}" needs an approved fact or the offer disclaimer '
            '"T&C apply."',
        }
        nearest = (
            f' The closest approved fact is {evidence[0].fact_id}: "{evidence[0].quote}".'
            if evidence
            else ""
        )
        return make_finding(
            rule,
            type="unsupported_claim",
            block=claim.block,
            start=hit.span.start,
            end=hit.span.end,
            text=hit.span.text,
            explanation=f"{reasons[hit.rule_code]}{nearest} ({rule.code}, {rule.source_ref})",
            confidence=0.95 if hit.rule_code in ("CLM-04", "CLM-06") else 0.9,
            detector="rules",
            evidence=evidence,
        )

    @staticmethod
    def _outdated_finding(
        claim: ClaimCandidate,
        record: ClaimRecord,
        scored: list[_Scored],
        ctx: ReviewContext,
        evidence: list[Evidence],
    ) -> Finding:
        rule = ctx.rules["CLM-03"]
        old = ctx.facts[record.fact_id or ""]
        current = ctx.facts[record.current_fact_id or ""]
        stale = next(s for s in scored if s.fact.id == old.id)
        start, end, text = claim.span.start, claim.span.end, claim.span.text
        suggestion: str | None = None
        family = stale.claim_q.family if stale.claim_q else None
        new_q = next((q for q in extract(current.statement) if q.family == family), None)
        if stale.claim_q and new_q:
            start = claim.span.start + stale.claim_q.span.start
            end = claim.span.start + stale.claim_q.span.end
            text = stale.claim_q.span.text
            suggestion = new_q.span.text
        current_evidence = Evidence(
            fact_id=current.id, quote=current.statement.rstrip("."), nli=None, score=None
        )
        return make_finding(
            rule,
            type="outdated_fact",
            block=claim.block,
            start=start,
            end=end,
            text=text,
            explanation=(
                f"This matches {old.id}, which was superseded by {current.id}"
                + (f" on {current.valid_from.isoformat()}" if current.valid_from else "")
                + f'. The current approved fact is: "{current.statement}" ({rule.code}, '
                f"{rule.source_ref})."
            ),
            confidence=record.confidence,
            suggestion=suggestion,
            detector="nli",
            evidence=[*evidence, current_evidence],
        )

    @staticmethod
    def _contradicted_finding(
        claim: ClaimCandidate,
        record: ClaimRecord,
        scored: list[_Scored],
        ctx: ReviewContext,
        evidence: list[Evidence],
    ) -> Finding:
        rule = ctx.rules["CLM-02"]
        fact = ctx.facts[record.fact_id or ""]
        best = next(s for s in scored if s.fact.id == fact.id)
        start, end, text = claim.span.start, claim.span.end, claim.span.text
        suggestion: str | None = None
        if best.numeric == "mismatch" and best.claim_q and best.fact_q:
            start = claim.span.start + best.claim_q.span.start
            end = claim.span.start + best.claim_q.span.end
            text = best.claim_q.span.text
            suggestion = (
                f"a {best.fact_q.span.text} fee"
                if best.claim_q.family == "fee" and best.claim_q.value == 0
                else best.fact_q.span.text
            )
        return make_finding(
            rule,
            type="contradicted_claim",
            block=claim.block,
            start=start,
            end=end,
            text=text,
            explanation=(
                f'This contradicts approved fact {fact.id}: "{fact.statement}" '
                f"({fact.source_ref}; {rule.code}, {rule.source_ref})."
            ),
            confidence=record.confidence,
            suggestion=suggestion,
            detector="nli",
            evidence=evidence,
        )


def _evidence(record: ClaimRecord, scored: list[_Scored]) -> list[Evidence]:
    if record.fact_id is None:
        return []
    best = next((s for s in scored if s.fact.id == record.fact_id), None)
    if best is None or not best.relevant:
        return []
    if best.candidate.dense is not None and best.candidate.dense < MIN_DENSE_EVIDENCE:
        return []  # too loosely related to show as evidence
    quote = record.quote or best_quote(record.hypothesis, best.fact.statement)
    return [
        Evidence(
            fact_id=best.fact.id,
            quote=quote or best.fact.statement.rstrip("."),
            nli=best.label,
            score=round(max(best.entail, best.contradict, best.nli["neutral"]), 3),
        )
    ]
