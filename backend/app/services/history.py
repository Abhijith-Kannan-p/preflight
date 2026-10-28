"""Generate a clearly fictional review history on first boot, so Insights, Guideline Health,
the Stale-Content Radar and the Creator Coach show real data on first open.

Each draft in data/seed/history.json goes through the real engine (deterministic mode: no
hosted LLM, and the Claim Ledger without the NLI model, which keeps this fast on a small
host). Some drafts are fixed by accepting suggestions and re-checked, some are disputed with
a written reason, some approved with an override. One entry publishes a reworded rule
version partway through, as a brand manager would. Timestamps span the past six weeks.

`HISTORY_VERSION` is stored in the template's settings; when the seed history changes, the
template is rebuilt once on the next boot.
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
    Rule,
    RuleStatus,
    Severity,
    Submission,
    SubmissionState,
    Workspace,
    utcnow,
)
from app.seed import WORKSPACE_ID
from app.services import runner
from app.workflow import apply_suggestions

log = logging.getLogger(__name__)
APPROVER = "usr_abhi4"
HISTORY_VERSION = 2


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
    runner.run_revision(revision_id, use_llm=False, use_nli=False)


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
            payload={"rule": finding.rule_code, "text": finding.text} if finding else {},
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


def publish_rule_version(session: Session, change: dict[str, Any]) -> None:
    """A brand manager rewords a rule: the old version is retired and a new one created."""
    when = utcnow() - timedelta(days=change["days_ago"], hours=5)
    current = session.scalar(
        select(Rule).where(
            Rule.workspace_id == WORKSPACE_ID,
            Rule.code == change["code"],
            Rule.status == RuleStatus.active,
        )
    )
    if current is None:
        return
    current.status = RuleStatus.retired
    session.add(
        Rule(
            workspace_id=WORKSPACE_ID,
            code=current.code,
            category=current.category,
            title=change["title"],
            description=change["description"],
            severity=current.severity,
            config=change["config"],
            source_doc=current.source_doc,
            source_page=current.source_page,
            version=current.version + 1,
            status=RuleStatus.active,
            created_by=change["by"],
            approved_by=change["by"],
            created_at=when,
        )
    )
    session.get_one(Workspace, WORKSPACE_ID).rulebook_version += 1
    audit.record(
        session,
        "rule",
        current.code,
        "rule_updated",
        change["by"],
        {"version": current.version + 1, "history": True, "title": change["title"]},
    )
    session.commit()


def _disputes(entry: dict[str, Any]) -> list[tuple[str, str]]:
    """`dispute` is a list of rule codes or of {rule, reason} objects."""
    found = []
    for item in entry.get("dispute", []):
        if isinstance(item, str):
            found.append((item, "Approved by legal in the campaign brief."))
        else:
            found.append((item["rule"], item["reason"]))
    return found


def create_entry(session: Session, entry: dict[str, Any]) -> None:
    if "rule_version" in entry:
        publish_rule_version(session, entry["rule_version"])
        return
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

    for rule_code, reason in _disputes(entry):
        finding = session.scalar(
            select(Finding).where(Finding.revision_id == latest.id, Finding.rule_code == rule_code)
        )
        if finding:
            finding.status = "disputed"
            _decide(
                session, submission, latest, "dispute", entry["author"], created, finding, reason
            )

    if entry.get("fix"):
        findings = list(session.scalars(select(Finding).where(Finding.revision_id == latest.id)))
        for f in findings:
            if f.suggestion and not f.needs_review and f.status == "open":
                f.status, f.applied_text = "accepted", str(f.suggestion["text"])
                _decide(session, submission, latest, "accept", entry["author"], created, f)
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
        if entry.get("override"):
            blocking = session.scalars(
                select(Finding).where(
                    Finding.revision_id == latest.id,
                    Finding.severity == Severity.critical,
                    Finding.needs_review.is_(False),
                    Finding.status.in_(("open", "disputed", "escalated")),
                )
            )
            for finding in blocking:
                finding.status = "resolved"
                _decide(
                    session,
                    submission,
                    latest,
                    "override",
                    APPROVER,
                    later + timedelta(minutes=50),
                    finding,
                    "Accepted for this post: the linked page carries the full terms.",
                )
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
        workspace = session.get(Workspace, WORKSPACE_ID)
        if workspace is None:
            return
        current = workspace.settings.get("history_version") == HISTORY_VERSION
        template = select(Submission.id).where(Submission.workspace_id == WORKSPACE_ID)
        has_history = session.scalar(template.limit(1)) is not None
        if has_history and current:
            return
        if has_history:
            # An older seed history: rebuild the template (it holds no visitor data).
            from app.ml.embeddings import get_embedder
            from app.seed import seed_all
            from app.services.sandbox import clear_workspace

            clear_workspace(session, WORKSPACE_ID)
            session.flush()
            seed_all(session, get_settings().seed_dir, get_embedder())
            workspace = session.get_one(Workspace, WORKSPACE_ID)
        entries = json.loads((get_settings().seed_dir / "history.json").read_text(encoding="utf-8"))
        workspace.settings = {**workspace.settings, "history_version": HISTORY_VERSION}
        # The seeded rulebook predates the history, so per-version metrics line up.
        oldest = max((e.get("days_ago", 0) for e in entries), default=0) + 7
        for rule in session.scalars(select(Rule).where(Rule.workspace_id == WORKSPACE_ID)):
            rule.created_at = utcnow() - timedelta(days=oldest)
        session.commit()
        for entry in entries:
            try:
                create_entry(session, entry)
            except Exception:
                log.exception("demo history entry %s failed", entry.get("title"))
                session.rollback()
        log.info("demo history created: %d reviews", len(entries))
