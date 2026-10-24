"""Brand Score = max(0, 100 - 25 x critical - 10 x major - 3 x minor), over open findings.

Findings waiting for a human look (confidence < 0.6) do not cost points until confirmed.
"""

from collections.abc import Iterable

from pydantic import BaseModel

from app.engine.schema import Finding

PENALTY: dict[str, int] = {"critical": 25, "major": 10, "minor": 3}
COUNTED_STATUSES = {"open", "escalated"}


class ScoreItem(BaseModel):
    finding_id: str
    rule_id: str
    severity: str
    points: int


class BrandScore(BaseModel):
    score: int
    breakdown: list[ScoreItem]


def brand_score(findings: Iterable[Finding]) -> BrandScore:
    items = [
        ScoreItem(
            finding_id=f.id, rule_id=f.rule.id, severity=f.severity, points=PENALTY[f.severity]
        )
        for f in findings
        if f.status in COUNTED_STATUSES and not f.needs_review
    ]
    items.sort(key=lambda i: -i.points)
    return BrandScore(score=max(0, 100 - sum(i.points for i in items)), breakdown=items)
