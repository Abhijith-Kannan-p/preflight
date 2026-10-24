"""Review Receipt: a shareable one-page record of an approved item. Public by link."""

from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_session
from app.models import (
    AuditEvent,
    Claim,
    Decision,
    Finding,
    Revision,
    Submission,
    SubmissionState,
    User,
)
from app.schemas.reviews import UserRef

router = APIRouter(prefix="/api", tags=["receipts"])


class ReceiptFinding(BaseModel):
    rule_id: str
    rule_source: str
    severity: str
    text: str
    status: str
    explanation: str
    needs_review: bool


class ReceiptDecision(BaseModel):
    kind: str
    actor: UserRef
    reason: str
    rule: str | None
    created_at: datetime


class Receipt(BaseModel):
    id: str
    title: str
    channel: str
    state: str
    author: UserRef
    approver: UserRef | None
    created_at: datetime
    approved_at: datetime | None
    revisions: int
    first_score: int | None
    final_score: int | None
    final_text: str
    checks: list[dict[str, Any]]
    findings_first: dict[str, int]
    findings_final: list[ReceiptFinding]
    claims: dict[str, int]
    overrides: list[ReceiptDecision]
    timeline: list[ReceiptDecision]
    ai: dict[str, Any]
    audit_intact: bool
    audit_message: str
    audit_events: int
    receipt_hash: str | None


def build_receipt(session: Session, review_id: str) -> Receipt:
    submission = session.get(Submission, review_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found.")
    if submission.state not in (SubmissionState.approved, SubmissionState.published):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A Review Receipt is issued once the content is approved.",
        )
    revisions = list(
        session.scalars(
            select(Revision)
            .where(Revision.submission_id == submission.id)
            .order_by(Revision.number)
        )
    )
    first, final = revisions[0], revisions[-1]

    def users(user_id: str | None) -> UserRef | None:
        user = session.get(User, user_id) if user_id else None
        return UserRef.model_validate(user) if user else None

    def findings(rev: Revision) -> list[Finding]:
        return list(
            session.scalars(
                select(Finding).where(Finding.revision_id == rev.id).order_by(Finding.position)
            )
        )

    decisions = [
        ReceiptDecision(
            kind=d.kind,
            actor=UserRef.model_validate(session.get_one(User, d.actor_id)),
            reason=d.reason,
            rule=str(d.payload.get("rule")) if d.payload.get("rule") else None,
            created_at=d.created_at,
        )
        for d in session.scalars(
            select(Decision)
            .where(Decision.submission_id == submission.id)
            .order_by(Decision.created_at)
        )
    ]
    chain = audit.verify_chain(session)
    last_event = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == submission.id)
        .order_by(AuditEvent.id.desc())
        .limit(1)
    ).first()
    claims = Counter(
        c.verdict for c in session.scalars(select(Claim).where(Claim.revision_id == final.id))
    )
    author = users(submission.author_id)
    assert author is not None
    return Receipt(
        id=submission.id,
        title=submission.title,
        channel=submission.channel,
        state=submission.state.value,
        author=author,
        approver=users(submission.approved_by),
        created_at=submission.created_at,
        approved_at=submission.approved_at,
        revisions=len(revisions),
        first_score=first.brand_score,
        final_score=final.brand_score,
        final_text=final.content,
        checks=final.report.get("checkers", []),
        findings_first=dict(Counter(f.severity.value for f in findings(first))),
        findings_final=[
            ReceiptFinding(
                rule_id=f.rule_code,
                rule_source=f.rule_source,
                severity=f.severity.value,
                text=f.text,
                status=f.status,
                explanation=f.explanation,
                needs_review=f.needs_review,
            )
            for f in findings(final)
        ],
        claims=dict(claims),
        overrides=[d for d in decisions if d.kind == "override"],
        timeline=[d for d in decisions if d.kind not in ("accept", "edit", "reopen")],
        ai=final.report.get("ai", {}),
        audit_intact=chain.intact,
        audit_message=chain.message,
        audit_events=chain.events,
        receipt_hash=last_event.hash if last_event else None,
    )


@router.get("/receipts/{review_id}", response_model=Receipt)
def receipt(review_id: str, session: Session = Depends(get_session)) -> Receipt:
    return build_receipt(session, review_id)


@router.get("/receipts/{review_id}/pdf", response_class=Response)
def receipt_pdf(review_id: str, session: Session = Depends(get_session)) -> Response:
    from app.services.receipt_pdf import render_receipt_pdf

    data = render_receipt_pdf(build_receipt(session, review_id))
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="preflight-receipt-{review_id}.pdf"'
        },
    )
