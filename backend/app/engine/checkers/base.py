"""Checker interface and a helper for building findings that cite their rule."""

from typing import Protocol

from app.engine.context import ReviewContext, RuleInfo
from app.engine.schema import (
    Detector,
    Evidence,
    Finding,
    FindingType,
    NormalisedDoc,
    RuleRef,
    SeverityLevel,
    Span,
    Suggestion,
)


class Checker(Protocol):
    name: str
    label: str

    async def run(self, doc: NormalisedDoc, ctx: ReviewContext) -> list[Finding]: ...


def make_finding(
    rule: RuleInfo,
    *,
    type: FindingType,
    block: int,
    start: int,
    end: int,
    text: str,
    explanation: str,
    confidence: float,
    suggestion: str | None = None,
    severity: SeverityLevel | None = None,
    detector: Detector = "rules",
    evidence: list[Evidence] | None = None,
) -> Finding:
    return Finding(
        type=type,
        span=Span(block=block, start=start, end=end),
        text=text,
        rule=RuleRef(id=rule.code, source=rule.source_ref),
        evidence=evidence or [],
        severity=severity or rule.severity,
        confidence=round(confidence, 3),
        explanation=explanation,
        suggestion=Suggestion(text=suggestion) if suggestion is not None else None,
        detector=detector,
    )
