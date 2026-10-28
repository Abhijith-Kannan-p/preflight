"""TerminologyChecker: product names (case-sensitive, exact and fuzzy) and banned words."""

import re

from rapidfuzz import fuzz

from app.engine.checkers.base import make_finding
from app.engine.context import ReviewContext, RuleInfo, TermInfo
from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import TextSpan, find_phrase, overlaps

FUZZY_THRESHOLD = 85
_TOKEN = re.compile(r"[A-Za-z][A-Za-z-]*")
# Web addresses, emails and domains are spelled as registered ("paywise.example"): not prose.
_ADDRESS = re.compile(
    r"https?://\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?![\w-])(?:/\S*)?",
)


class _Taken:
    """Character ranges already explained, so one span never gets two terminology findings.
    Web addresses start out taken: they are not checked at all."""

    def __init__(self, text: str = "") -> None:
        self._ranges: list[tuple[int, int]] = [
            (m.start(), m.end()) for m in _ADDRESS.finditer(text)
        ]

    def claim(self, span: TextSpan) -> bool:
        if self.has(span):
            return False
        self._ranges.append((span.start, span.end))
        return True

    def has(self, span: TextSpan) -> bool:
        return any(overlaps((span.start, span.end), r) for r in self._ranges)


class TerminologyChecker:
    name = "terminology"
    label = "Terminology and product names"

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]:
        findings: list[Finding] = []
        for block in doc.blocks:
            findings += self._product_names(block.id, block.text, ctx)
            findings += self._banned(block.id, block.text, ctx)
        return findings

    def _product_names(self, block_id: int, text: str, ctx: ReviewContext) -> list[Finding]:
        rule = ctx.rule("TRM-02")
        if rule is None:
            return []
        # Longest names first so "Paywise Business" is one finding, not two.
        names = sorted(
            (t for t in ctx.terms if t.kind == "product_name"), key=lambda t: -len(t.term)
        )
        taken = _Taken(text)
        findings: list[Finding] = []
        for term in names:
            for candidate in (term.term, *term.variants):
                for match in find_phrase(text, candidate, case_sensitive=False):
                    correct = match.text == term.term
                    if taken.claim(match) and not correct:
                        findings.append(_name_finding(rule, block_id, match, term, 0.97))

        single_word_names = [t for t in names if " " not in t.term]
        for m in _TOKEN.finditer(text):
            token = TextSpan(m.start(), m.end(), m.group(0))
            if taken.has(token):
                continue
            for term in single_word_names:
                score = fuzz.ratio(token.text.lower(), term.term.lower())
                if score >= FUZZY_THRESHOLD and taken.claim(token):
                    findings.append(_name_finding(rule, block_id, token, term, 0.9 * score / 100))
                    break
        return findings

    def _banned(self, block_id: int, text: str, ctx: ReviewContext) -> list[Finding]:
        terms = sorted(
            (t for t in ctx.terms if t.kind in ("banned", "discouraged")),
            key=lambda t: -len(t.term),
        )
        taken = _Taken(text)
        findings: list[Finding] = []
        for term in terms:
            rule = ctx.rule(term.rule_code)
            if rule is None:
                continue
            for match in find_phrase(text, term.term, term.case_sensitive):
                if taken.claim(match):
                    findings.append(_banned_finding(rule, block_id, match, term))
        return findings


def _name_finding(
    rule: RuleInfo, block_id: int, match: TextSpan, term: TermInfo, confidence: float
) -> Finding:
    return make_finding(
        rule,
        type="terminology",
        block=block_id,
        start=match.start,
        end=match.end,
        text=match.text,
        explanation=(
            f'The product name "{match.text}" should be written "{term.term}". '
            f"{rule.code} requires approved spelling and capitalisation ({rule.source_ref})."
        ),
        confidence=confidence,
        suggestion=term.term,
    )


def _banned_finding(rule: RuleInfo, block_id: int, match: TextSpan, term: TermInfo) -> Finding:
    banned = term.kind == "banned"
    advice = (
        f' Use "{term.replacement}" instead.' if term.replacement else " Remove or rephrase it."
    )
    return make_finding(
        rule,
        type="banned_phrase",
        block=block_id,
        start=match.start,
        end=match.end,
        text=match.text,
        explanation=(
            f'"{match.text}" is {"a banned" if banned else "a discouraged"} phrase under '
            f"{rule.code} ({rule.source_ref}).{advice}"
        ),
        confidence=0.95 if banned else 0.8,
        suggestion=_match_case(term.replacement, match.text) if term.replacement else None,
        severity=None if banned else "minor",
    )


def _match_case(replacement: str, original: str) -> str:
    return replacement[:1].upper() + replacement[1:] if original[:1].isupper() else replacement
