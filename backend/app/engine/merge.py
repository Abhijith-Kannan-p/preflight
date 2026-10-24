"""Merge and rank findings from all checkers.

Two findings are duplicates when they cite the same rule on overlapping text, or when they
cover nearly the same span (IoU >= 0.8). The higher-ranked one is kept and the other is
attached as `related`. Different rules on partly overlapping text stay separate, because
each is a distinct problem the author needs to fix (e.g. CLM-01 and CLM-04 on one phrase).
"""

from app.engine.schema import SEVERITY_WEIGHT, Finding

CONFIDENCE_THRESHOLD = 0.6


def _iou(a: Finding, b: Finding) -> float:
    if a.span.block != b.span.block:
        return 0.0
    inter = min(a.span.end, b.span.end) - max(a.span.start, b.span.start)
    if inter <= 0:
        return 0.0
    union = max(a.span.end, b.span.end) - min(a.span.start, b.span.start)
    return inter / union


def _duplicates(a: Finding, b: Finding) -> bool:
    iou = _iou(a, b)
    return (a.rule.id == b.rule.id and iou > 0) or (iou >= 0.8 and a.type == b.type)


def merge_findings(findings: list[Finding]) -> list[Finding]:
    ranked = sorted(findings, key=lambda f: (-f.rank, f.span.block, f.span.start))
    kept: list[Finding] = []
    for finding in ranked:
        primary = next((k for k in kept if _duplicates(k, finding)), None)
        if primary is None:
            kept.append(finding)
        else:
            primary.related.append(finding.id)
    for finding in kept:
        finding.needs_review = finding.confidence < CONFIDENCE_THRESHOLD
    return sorted(
        kept,
        key=lambda f: (f.needs_review, -SEVERITY_WEIGHT[f.severity], -f.confidence, f.span.block),
    )
