"""Claim detection, optimised for recall.

Deterministic detection finds checkable statements (numbers, product capabilities) and the
risky phrases the claim rules name (superlatives, absolutes, guarantees, "free"). An LLM
extractor can add more claims; candidates are unioned and de-duplicated by span.
"""

import re
from dataclasses import dataclass, field

from app.engine.context import ReviewContext
from app.engine.schema import NormalisedDoc
from app.engine.text import TextSpan, find_phrase, overlaps, sentences

# Verbs that make a sentence about the brand a factual, checkable statement.
_FACT_VERBS = re.compile(
    r"\b(is|are|was|has|have|offers?|serves?|settles?|supports?|provides?|processes?|charges?|"
    r"carr(?:y|ies)|secures?|protects?|uses?|requires?|resolves?|maintains?|reach(?:es)?|"
    r"regulated|regulates|certified|available|rated|founded|headquartered|guarantees?|pay|get|"
    r"earn|protected|encrypted|works?|keeps?|makes?|gives?|goes|go|plans?|launch(?:es)?|"
    r"integrates?|includes?|accepts?|handles?|approves?|answers?|rewards?|saves?|partnered|"
    r"trusted|used|named|won|crossed|announced)\b",
    re.IGNORECASE,
)
_HAS_NUMBER = re.compile(r"\d|%|\b(zero|one|two|three|five|ten|twelve|thirty)\b", re.IGNORECASE)
_DATELINE = re.compile(r"^[A-Z][a-z]+,\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\.?$")
_CLAUSE_SPLIT = re.compile(r",\s+and\s+|;\s+|\s+while\s+")
_RELATIVE = re.compile(r"^(?P<subj>[A-Z][\w ]{1,40}?),\s+which\s+(?P<rel>[^,]+),\s+(?P<rest>.+)$")
_POSSESSIVE_BEFORE = re.compile(r"[A-Z][\w]*['\u2019]s\s+$")

PATTERN_RULES = {"CLM-01": "superlative", "CLM-04": "absolute", "CLM-06": "guarantee",
                 "CLM-08": "offer"}  # fmt: skip


@dataclass
class PatternHit:
    rule_code: str
    span: TextSpan


@dataclass
class ClaimCandidate:
    block: int
    span: TextSpan
    hypothesis: str
    claim_type: str
    hits: list[PatternHit] = field(default_factory=list)
    source: str = "rules"


def _brand_terms(ctx: ReviewContext) -> list[str]:
    return [t.term for t in ctx.terms if t.kind == "product_name"] + ["UPI", "we", "our"]


def _clauses(sentence: TextSpan) -> list[tuple[TextSpan, str]]:
    """Split a sentence into atomic clauses: (span in block, hypothesis text)."""
    text = sentence.text
    rel = _RELATIVE.match(text)
    if rel:
        subj = rel.group("subj")
        base = sentence.start
        return [
            (TextSpan(base + rel.start("rel"), base + rel.end("rel"), rel.group("rel")),
             f"{subj} {rel.group('rel')}"),
            (TextSpan(base + rel.start("rest"), base + rel.end("rest"), rel.group("rest")),
             f"{subj} {rel.group('rest')}"),
        ]  # fmt: skip
    bounds: list[tuple[int, int]] = []
    start = 0
    for m in _CLAUSE_SPLIT.finditer(text):
        bounds.append((start, m.start()))
        start = m.end()
    bounds.append((start, len(text)))
    clauses: list[tuple[TextSpan, str]] = []
    for a, b in bounds:
        piece = text[a:b].strip()
        if not piece:
            continue
        offset = text.index(piece, a)
        span = TextSpan(sentence.start + offset, sentence.start + offset + len(piece), piece)
        clauses.append((span, piece))
    return clauses


def _pattern_hits(text: str, offset: int, ctx: ReviewContext) -> list[PatternHit]:
    hits: list[PatternHit] = []
    for code in PATTERN_RULES:
        rule = ctx.rule(code)
        if rule is None:
            continue
        taken: list[tuple[int, int]] = []
        for phrase in sorted(rule.config.get("patterns", []), key=len, reverse=True):
            for m in find_phrase(text, phrase):
                if any(overlaps((m.start, m.end), t) for t in taken):
                    continue
                taken.append((m.start, m.end))
                start = m.start
                possessive = _POSSESSIVE_BEFORE.search(text[: m.start])
                if code == "CLM-01" and possessive:
                    start = possessive.start()  # "India's #1", not just "#1"
                hits.append(
                    PatternHit(code, TextSpan(offset + start, offset + m.end, text[start : m.end]))
                )
    return hits


def detect_claims(doc: NormalisedDoc, ctx: ReviewContext) -> list[ClaimCandidate]:
    brand = _brand_terms(ctx)
    candidates: list[ClaimCandidate] = []
    for block in doc.blocks:
        for sentence in sentences(block.text):
            if _DATELINE.match(sentence.text.strip()):
                continue
            for span, hypothesis in _clauses(sentence):
                hits = _pattern_hits(span.text, span.start, ctx)
                mentions_brand = any(
                    next(find_phrase(hypothesis, b), None) for b in brand
                ) or hypothesis.lower().startswith(("with ", "every ", "it "))
                has_verb = bool(_FACT_VERBS.search(hypothesis))
                factual = mentions_brand and has_verb
                numeric = bool(_HAS_NUMBER.search(span.text))
                if not (hits or factual or numeric):
                    continue
                claim_type = (
                    PATTERN_RULES[hits[0].rule_code]
                    if hits
                    else "numeric"
                    if numeric
                    else "factual"
                )
                candidates.append(ClaimCandidate(block.id, span, hypothesis, claim_type, hits))
    return candidates


def union(primary: list[ClaimCandidate], extra: list[ClaimCandidate]) -> list[ClaimCandidate]:
    """Add extra (e.g. LLM-extracted) claims that do not overlap an existing candidate."""
    merged = list(primary)
    for candidate in extra:
        clash = any(
            c.block == candidate.block
            and overlaps((c.span.start, c.span.end), (candidate.span.start, candidate.span.end))
            for c in merged
        )
        if not clash:
            merged.append(candidate)
    return merged
