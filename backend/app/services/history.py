"""Generate a small, clearly fictional review history on first boot so Insights has data.

Each draft in data/seed/history.json goes through the real engine (deterministic mode, no
hosted LLM). Some are fixed by accepting suggestions and re-checked, some are disputed,
submitted and approved. Timestamps are spread over the past three weeks.
"""

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.db import SessionLocal
from app.engine.normalise import from_text
from app.models import (
    Decision,
    Finding,
    Revision,
    Submission,
    SubmissionState,
    utcnow,
)
from app.seed import WORKSPACE_ID
from app.services import runner
from app.workflow import apply_suggestions

log = logging.getLogger(__name__)
APPROVER = "usr_abhi4"


def _new_revision(
    session: Session, submission: Submission, text: str, number: int, author: str
) -> Revision:
    doc = from_text(text)
    revision = Revision(
        submission_id=submission.id,
        number=number,
        content=doc.text,
        source_format=doc.source_format,
        normalised_doc=doc.model_dump(),
        content_hash=hashlib.sha256(doc.text.encode()).hexdigest(),
        created_by=author,
    )
    session.add(revision)
    session.commit()
    return revision


def _run(revision_id: str) -> None:
    runner.run_revision(revision_id, use_llm=False)


def _decide(
    session: Session,
    submission: Submission,
    revision: Revision,
    kind: str,
    actor: str,
    when: Any,
    finding: Finding | None = None,
    reason: str = "",
) -> None:
    session.add(
        Decision(
            submission_id=submission.id,
            revision_id=revision.id,
            finding_id=finding.id if finding else None,
            kind=kind,
            reason=reason,
            actor_id=actor,
            created_at=when,
            payload={"rule": finding.rule_code} if finding else {},
        )
    )
    audit.record(
        session,
        "submission",
        submission.id,
        kind,
        actor,
        {"history": True, "rule": finding.rule_code if finding else None},
    )


def create_entry(session: Session, entry: dict[str, Any]) -> None:
    created = utcnow() - timedelta(days=entry["days_ago"], hours=3)
    submission = Submission(
        workspace_id=WORKSPACE_ID,
        author_id=entry["author"],
        channel=entry["channel"],
        title=entry["title"],
        created_at=created,
        updated_at=created,
    )
    session.add(submission)
    session.commit()
    first = _new_revision(session, submission, entry["content"], 1, entry["author"])
    _run(first.id)
    session.expire_all()
    latest = session.get_one(Revision, first.id)

    for rule_code in entry.get("dispute", []):
        finding = session.scalar(
            select(Finding).where(Finding.revision_id == latest.id, Finding.rule_code == rule_code)
        )
        if finding:
            finding.status = "disputed"
            _decide(
                session,
                submission,
                latest,
                "dispute",
                entry["author"],
                created,
                finding,
                "Approved by legal in the campaign brief.",
            )

    if entry.get("fix"):
        findings = list(session.scalars(select(Finding).where(Finding.revision_id == latest.id)))
        for f in findings:
            if f.suggestion and not f.needs_review and f.status == "open":
                f.status, f.applied_text = "accepted", str(f.suggestion["text"])
        session.commit()
        blocks = [b["text"] for b in latest.normalised_doc["blocks"]]
        fixed, _ = apply_suggestions(blocks, findings)
        second = _new_revision(
            session, submission, "\n\n".join(b for b in fixed if b), 2, entry["author"]
        )
        _run(second.id)
        session.expire_all()
        latest = session.get_one(Revision, second.id)

    for rev in session.scalars(select(Revision).where(Revision.submission_id == submission.id)):
        rev.created_at = rev.completed_at = created + timedelta(minutes=10 * rev.number)

    outcome = entry["outcome"]
    later = created + timedelta(hours=2)
    if outcome in ("approved", "in_review", "changes_requested"):
        _decide(session, submission, latest, "submit", entry["author"], later)
        submission.state = SubmissionState.in_review
    if outcome == "approved":
        _decide(session, submission, latest, "approve", APPROVER, later + timedelta(hours=1))
        submission.state = SubmissionState.approved
        submission.approved_by, submission.approved_at = APPROVER, later + timedelta(hours=1)
    if outcome == "changes_requested":
        _decide(
            session,
            submission,
            latest,
            "request_changes",
            APPROVER,
            later,
            reason="Please remove the superlative and use the current settlement time.",
        )
        submission.state = SubmissionState.changes_requested
    submission.updated_at = later
    session.commit()


def ensure_demo_history() -> None:
    with SessionLocal() as session:
        if session.scalar(select(Submission.id).limit(1)) is not None:
            return
        entries = json.loads((get_settings().seed_dir / "history.json").read_text(encoding="utf-8"))
        for entry in entries:
            try:
                create_entry(session, entry)
            except Exception:
                log.exception("demo history entry %s failed", entry.get("title"))
                session.rollback()
        log.info("demo history created: %d reviews", len(entries))
