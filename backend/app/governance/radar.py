"""Stale-Content Radar: approved content whose facts have changed since it was cleared.

The fact-dependency index comes from the Claim Ledger's evidence on cleared (approved or
published) items: item → the revision that was cleared → each claim → the approved fact it
relied on, with the fact's wording at review time. A dependency is stale when that fact has
since been superseded, edited, retired, or has passed its valid-until date.

It is computed straight from the database, so a fact change shows up on the Radar on the next
request; `notify_affected` is also called synchronously by every fact edit, supersession and
retirement, so authors and brand managers get a notification in the same request.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    Fact,
    Revision,
    Role,
    RuleStatus,
    Submission,
    SubmissionState,
    User,
)
from app.services.notify import notify_users

CLEARED = (SubmissionState.approved, SubmissionState.published)


@dataclass(frozen=True)
class Dependency:
    submission_id: str
    title: str
    state: str
    cleared_at: datetime | None
    author_id: str
    sentence: str
    fact_id: str
    quoted: str | None


def dependencies(session: Session, workspace_id: str) -> list[Dependency]:
    """Every (cleared item, claim, fact) triple in the workspace."""
    cleared = session.scalars(
        select(Submission).where(
            Submission.workspace_id == workspace_id, Submission.state.in_(CLEARED)
        )
    ).all()
    found: list[Dependency] = []
    for submission in cleared:
        revision = session.scalar(
            select(Revision)
            .where(Revision.submission_id == submission.id)
            .order_by(Revision.number.desc())
            .limit(1)
        )
        if revision is None:
            continue
        for claim in session.scalars(select(Claim).where(Claim.revision_id == revision.id)):
            for fact_id in {claim.fact_id, claim.current_fact_id} - {None}:
                found.append(
                    Dependency(
                        submission.id,
                        submission.title,
                        submission.state.value,
                        submission.approved_at,
                        submission.author_id,
                        claim.text,
                        str(fact_id),
                        claim.quote,
                    )
                )
    return found


def _change(fact: Fact, cleared_at: datetime | None, today: date) -> str | None:
    if fact.superseded_by:
        return "superseded"
    if fact.status == RuleStatus.retired:
        return "retired"
    if fact.valid_until and fact.valid_until < today:
        return "expired"
    if cleared_at and fact.updated_at and fact.updated_at > cleared_at and fact.version > 1:
        return "edited"
    return None


def stale(
    session: Session, workspace_id: str, fact_id: str | None = None, today: date | None = None
) -> list[dict[str, Any]]:
    """Radar entries: cleared items relying on a fact that has changed since."""
    on = today or date.today()
    facts = {
        f.id: f for f in session.scalars(select(Fact).where(Fact.workspace_id == workspace_id))
    }
    entries: list[dict[str, Any]] = []
    for dep in dependencies(session, workspace_id):
        if fact_id and dep.fact_id != fact_id:
            continue
        fact = facts.get(dep.fact_id)
        if fact is None:
            continue
        change = _change(fact, dep.cleared_at, on)
        if change is None:
            continue
        replacement = facts.get(fact.superseded_by or "") if fact.superseded_by else None
        entries.append(
            {
                "submission_id": dep.submission_id,
                "title": dep.title,
                "state": dep.state,
                "cleared_at": dep.cleared_at,
                "sentence": dep.sentence,
                "fact_id": dep.fact_id,
                "change": change,
                "old_value": dep.quoted or fact.statement,
                "new_fact_id": replacement.id if replacement else None,
                "new_value": replacement.statement
                if replacement
                else (fact.statement if change == "edited" else None),
                "changed_at": (replacement.updated_at if replacement else fact.updated_at),
            }
        )
    entries.sort(key=lambda e: (e["fact_id"], e["title"]))
    return entries


def notify_affected(session: Session, workspace_id: str, fact_id: str) -> int:
    """Tell authors and brand managers which cleared items a fact change affects."""
    affected = stale(session, workspace_id, fact_id)
    by_item: dict[str, dict[str, Any]] = {e["submission_id"]: e for e in affected}
    if not by_item:
        return 0
    managers = session.scalars(
        select(User.id).where(User.workspace_id == workspace_id, User.role == Role.brand_manager)
    ).all()
    authors = {
        row.id: row.author_id
        for row in session.execute(
            select(Submission.id, Submission.author_id).where(Submission.id.in_(by_item))
        )
    }
    for submission_id, entry in by_item.items():
        notify_users(
            session,
            {authors[submission_id], *managers},
            "stale_content",
            f'{fact_id} changed ({entry["change"]}): "{entry["title"]}" relies on it. '
            "Open the Stale-Content Radar to re-check it.",
            submission_id,
        )
    return len(by_item)
