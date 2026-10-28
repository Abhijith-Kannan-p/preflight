"""Creator Coach: each author's recurring mistakes, whether they are improving, and two or three
targeted tips before they write.

Definitions (first drafts only, "needs a human look" findings excluded):
- a *repeat mistake* is a first-draft finding whose rule already appeared in one of the same
  author's earlier first drafts;
- the *repeat-mistake rate* is repeat mistakes divided by all first-draft findings;
- the *baseline* is that rate over the author's older half of submissions, *recent* over the
  newer half. The Round 3 target is a 25% lower recent rate than the baseline.

Tips are deterministic: the rule's own guidance, the brand-approved wording for it (the rule's
fallback, a terminology replacement or a required disclaimer) and the author's own latest
example with the fix they accepted. No LLM is needed, so the Coach works offline.
"""

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Permission, can
from app.models import Finding, Revision, Rule, RuleStatus, Submission, Term, User

TREND_MARGIN = 0.1


def _first_drafts(session: Session, workspace_id: str, author_id: str) -> list[dict[str, Any]]:
    subs = session.scalars(
        select(Submission)
        .where(Submission.workspace_id == workspace_id, Submission.author_id == author_id)
        .order_by(Submission.created_at)
    ).all()
    drafts = []
    for submission in subs:
        first = session.scalar(
            select(Revision).where(Revision.submission_id == submission.id, Revision.number == 1)
        )
        if first is None or first.review_status != "complete":
            continue
        findings = [
            f
            for f in session.scalars(select(Finding).where(Finding.revision_id == first.id))
            if not f.needs_review
        ]
        drafts.append({"submission": submission, "findings": findings})
    return drafts


def _approved_wording(session: Session, workspace_id: str, rule: Rule, text: str) -> str | None:
    fallback = rule.config.get("fallback")
    if isinstance(fallback, str):
        return fallback
    disclaimer = rule.config.get("disclaimer")
    if isinstance(disclaimer, str):
        return f'add "{disclaimer}"'
    term = session.scalar(
        select(Term).where(Term.workspace_id == workspace_id, Term.rule_code == rule.code)
    )
    if term and rule.code == "TRM-02":
        return f'write "{term.term}"' if text else None
    if term and term.replacement:
        return f'use "{term.replacement}" instead of "{term.term}"'
    return None


def profile(session: Session, workspace_id: str, user: User) -> dict[str, Any]:
    drafts = _first_drafts(session, workspace_id, user.id)
    seen: set[str] = set()
    per_draft = []
    rule_counts: Counter[str] = Counter()
    examples: dict[str, Finding] = {}
    for draft in drafts:
        draft_rules = {f.rule_code for f in draft["findings"]}
        repeats = sum(1 for f in draft["findings"] if f.rule_code in seen)
        per_draft.append(
            {
                "title": draft["submission"].title,
                "date": draft["submission"].created_at,
                "findings": len(draft["findings"]),
                "repeats": repeats,
                "rules": sorted(draft_rules),
            }
        )
        for f in draft["findings"]:
            examples[f.rule_code] = f
        rule_counts.update(draft_rules)
        seen |= draft_rules

    def rate(rows: list[dict[str, Any]]) -> float | None:
        total = sum(r["findings"] for r in rows)
        return round(sum(r["repeats"] for r in rows) / total, 3) if total else None

    half = len(per_draft) // 2
    baseline, recent = rate(per_draft[:half]), rate(per_draft[half:])
    overall = rate(per_draft)
    trend = "not enough history"
    if baseline is not None and recent is not None:
        if recent <= baseline * (1 - TREND_MARGIN):
            trend = "improving"
        elif recent >= baseline:
            trend = "repeating"
        else:
            trend = "steady"

    rules = {
        r.code: r
        for r in session.scalars(
            select(Rule).where(Rule.workspace_id == workspace_id, Rule.status == RuleStatus.active)
        )
    }
    recurring = [(code, n) for code, n in rule_counts.most_common() if n >= 2 and code in rules]
    tips = []
    for code, count in recurring[:3]:
        rule = rules[code]
        example = examples.get(code)
        accepted = (
            example.applied_text if example and example.status in ("accepted", "edited") else None
        )
        tips.append(
            {
                "rule": code,
                "title": rule.title,
                "times": count,
                "guidance": rule.description,
                "approved_wording": _approved_wording(
                    session, workspace_id, rule, example.text if example else ""
                ),
                "your_example": example.text if example else None,
                "your_fix": accepted,
                "source_ref": rule.source_ref,
            }
        )
    weekly: dict[str, list[int]] = defaultdict(list)
    for row in per_draft:
        weekly[row["date"].strftime("%G-W%V")].append(row["findings"])
    return {
        "user": {"id": user.id, "name": user.name, "title": user.title},
        "submissions": len(per_draft),
        "repeat_rate": overall,
        "baseline_rate": baseline,
        "recent_rate": recent,
        "trend": trend,
        "recurring": [{"rule": c, "title": rules[c].title, "drafts": n} for c, n in recurring[:6]],
        "tips": tips,
        "weekly": [
            {"week": week, "drafts": len(v), "findings_per_draft": round(sum(v) / len(v), 2)}
            for week, v in sorted(weekly.items())
        ],
        "drafts": per_draft[-8:],
    }


def team(session: Session, workspace_id: str) -> list[dict[str, Any]]:
    authors = [
        u
        for u in session.scalars(select(User).where(User.workspace_id == workspace_id))
        if can(u, Permission.submit_content)
    ]
    return [profile(session, workspace_id, u) for u in authors]
