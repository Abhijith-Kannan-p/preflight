"""Basic governance insights: what goes wrong, which rules trigger, which get disputed, and
whether Brand Scores improve over time."""

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Permission, require
from app.db import get_session
from app.models import (
    Decision,
    Finding,
    Revision,
    Rule,
    RuleStatus,
    Submission,
    SubmissionState,
    User,
)

router = APIRouter(prefix="/api", tags=["insights"])


class Insights(BaseModel):
    totals: dict[str, float | int]
    by_type: list[dict[str, Any]]
    top_rules: list[dict[str, Any]]
    dispute_rates: list[dict[str, Any]]
    trend: list[dict[str, Any]]
    authors: list[dict[str, Any]]


@router.get("/insights", response_model=Insights)
def insights(
    user: User = Depends(require(Permission.view_insights)),
    session: Session = Depends(get_session),
) -> Insights:
    titles = {
        r.code: r.title
        for r in session.scalars(select(Rule).where(Rule.status == RuleStatus.active))
    }
    submissions = list(session.scalars(select(Submission)))
    revisions = list(session.scalars(select(Revision).where(Revision.review_status == "complete")))
    by_submission: dict[str, list[Revision]] = defaultdict(list)
    for rev in revisions:
        by_submission[rev.submission_id].append(rev)
    firsts = {sid: min(revs, key=lambda r: r.number) for sid, revs in by_submission.items()}
    lasts = {sid: max(revs, key=lambda r: r.number) for sid, revs in by_submission.items()}

    first_ids = {r.id for r in firsts.values()}
    all_findings = list(session.scalars(select(Finding)))
    first_findings = [f for f in all_findings if f.revision_id in first_ids and not f.needs_review]

    by_type = Counter(f.type for f in first_findings)
    by_rule = Counter(f.rule_code for f in first_findings)
    severity_by_rule = {f.rule_code: f.severity.value for f in first_findings}

    disputes = Counter(
        str(d.payload.get("rule"))
        for d in session.scalars(select(Decision).where(Decision.kind == "dispute"))
    )
    raised = Counter(f.rule_code for f in all_findings if not f.needs_review)

    trend_points: dict[date, list[tuple[int, int]]] = defaultdict(list)
    for sid, first in firsts.items():
        if first.brand_score is None or lasts[sid].brand_score is None:
            continue
        trend_points[first.created_at.date()].append(
            (first.brand_score, lasts[sid].brand_score or 0)
        )

    authors: dict[str, dict[str, Any]] = {}
    names = {u.id: u.name for u in session.scalars(select(User))}
    for submission in submissions:
        first_rev = firsts.get(submission.id)
        entry = authors.setdefault(
            submission.author_id,
            {"author": names.get(submission.author_id), "reviews": 0, "findings": 0, "scores": []},
        )
        entry["reviews"] += 1
        if first_rev:
            entry["findings"] += sum(1 for f in first_findings if f.revision_id == first_rev.id)
            if first_rev.brand_score is not None:
                entry["scores"].append(first_rev.brand_score)

    improvements: list[int] = []
    for sid, first in firsts.items():
        first_score, last_score = first.brand_score, lasts[sid].brand_score
        if first_score is not None and last_score is not None:
            improvements.append(last_score - first_score)
    dispute_rows: list[dict[str, Any]] = [
        {
            "rule": r,
            "title": titles.get(r, r),
            "raised": raised[r],
            "disputed": disputes[r],
            "rate": round(disputes[r] / raised[r], 2),
        }
        for r in raised
        if raised[r]
    ]
    dispute_rows.sort(key=lambda d: (-float(d["rate"]), -int(d["raised"])))
    return Insights(
        totals={
            "reviews": len(submissions),
            "approved": sum(
                s.state in (SubmissionState.approved, SubmissionState.published)
                for s in submissions
            ),
            "findings": len(first_findings),
            "critical_caught": sum(f.severity.value == "critical" for f in first_findings),
            "avg_improvement": round(sum(improvements) / len(improvements), 1)
            if improvements
            else 0,
        },
        by_type=[{"type": t, "count": n} for t, n in by_type.most_common()],
        top_rules=[
            {"rule": r, "title": titles.get(r, r), "count": n, "severity": severity_by_rule.get(r)}
            for r, n in by_rule.most_common(8)
        ],
        dispute_rates=dispute_rows[:8],
        trend=[
            {
                "date": d.isoformat(),
                "first": round(sum(p[0] for p in pts) / len(pts)),
                "final": round(sum(p[1] for p in pts) / len(pts)),
                "reviews": len(pts),
            }
            for d, pts in sorted(trend_points.items())
        ],
        authors=[
            {
                "author": e["author"],
                "reviews": e["reviews"],
                "findings": e["findings"],
                "avg_first_score": round(sum(e["scores"]) / len(e["scores"]))
                if e["scores"]
                else None,
            }
            for e in authors.values()
        ],
    )
