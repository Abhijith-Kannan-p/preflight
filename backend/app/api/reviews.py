"""Review API: create, stream progress, decide on findings, re-check, diff and transition."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth import Permission, can, current_user, permissions_for, require
from app.config import get_settings
from app.db import get_session
from app.engine.normalise import IntakeError, from_text, from_upload
from app.engine.schema import NormalisedDoc
from app.models import (
    ChannelProfile,
    Claim,
    Comment,
    Decision,
    Finding,
    Revision,
    Role,
    SampleDraft,
    Submission,
    SubmissionState,
    User,
    utcnow,
)
from app.schemas.reviews import (
    ClaimOut,
    CommentIn,
    CommentOut,
    CreatedReview,
    DecisionIn,
    DecisionOut,
    DiffOut,
    DraftOut,
    FindingOut,
    Gate,
    RecheckIn,
    ReviewListItem,
    ReviewOut,
    RevisionOut,
    RevisionSummary,
    SubmissionOut,
    TransitionIn,
    UserRef,
)
from app.seed import WORKSPACE_ID
from app.services import runner
from app.services.events import TERMINAL, bus
from app.services.notify import notify_roles, notify_users
from app.workflow import (
    TransitionError,
    apply_suggestions,
    blocking_criticals,
    check_transition,
)

router = APIRouter(prefix="/api", tags=["reviews"])

EDITABLE_STATES = {SubmissionState.draft, SubmissionState.changes_requested}


# --- helpers ---------------------------------------------------------------------------


def _conflict(message: str, **extra: object) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"message": message, **extra})


def _submission(session: Session, review_id: str) -> Submission:
    submission = session.get(Submission, review_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found.")
    return submission


def _latest(session: Session, submission: Submission) -> Revision:
    revision = session.scalar(
        select(Revision)
        .where(Revision.submission_id == submission.id)
        .order_by(Revision.number.desc())
        .limit(1)
    )
    if revision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review has no revisions.")
    return revision


def _findings(session: Session, revision_id: str) -> list[Finding]:
    return list(
        session.scalars(
            select(Finding).where(Finding.revision_id == revision_id).order_by(Finding.position)
        )
    )


def _finding_out(f: Finding) -> FindingOut:
    return FindingOut(
        id=f.id,
        type=f.type,
        span=f.span,
        text=f.text,
        rule={"id": f.rule_code, "source": f.rule_source},
        evidence=f.evidence,
        severity=f.severity.value,
        confidence=f.confidence,
        explanation=f.explanation,
        suggestion=f.suggestion,
        detector=f.detector,
        status=f.status,
        needs_review=f.needs_review,
        related=f.related,
        applied_text=f.applied_text,
    )


def _user_ref(user: User | None) -> UserRef | None:
    return UserRef.model_validate(user) if user else None


def _gate(submission: Submission, revision: Revision, findings: list[Finding]) -> Gate:
    if revision.review_status != "complete":
        return Gate(
            can_submit=False,
            can_approve=False,
            blocking=[],
            message="Preflight is still checking this revision.",
        )
    for_submit = blocking_criticals(findings, "submit")
    for_approve = blocking_criticals(findings, "approve")
    can_submit = submission.state in EDITABLE_STATES and not for_submit
    message = (
        f"{len(for_submit)} critical finding(s) must be fixed, disputed or escalated before "
        "you can submit."
        if for_submit
        else f"{len(for_approve)} critical finding(s) are disputed; approving needs an override "
        "reason for each."
        if for_approve
        else "No open critical findings."
    )
    return Gate(
        can_submit=can_submit,
        can_approve=submission.state == SubmissionState.in_review,
        blocking=[f.id for f in for_approve],
        message=message,
    )


def _content_hash(doc: NormalisedDoc) -> str:
    return hashlib.sha256(doc.text.encode()).hexdigest()


def _new_revision(
    session: Session,
    submission: Submission,
    doc: NormalisedDoc,
    user: User,
    number: int,
    content_uri: str | None = None,
) -> Revision:
    revision = Revision(
        submission_id=submission.id,
        number=number,
        content=doc.text,
        content_uri=content_uri,
        source_format=doc.source_format,
        normalised_doc=doc.model_dump(),
        content_hash=_content_hash(doc),
        created_by=user.id,
    )
    session.add(revision)
    session.flush()
    return revision


def _require_author(user: User, submission: Submission) -> None:
    if not can(user, Permission.submit_content):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only content authors can do this.")
    if user.role == Role.creator and submission.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the author can change this draft.")


# --- create and read -------------------------------------------------------------------


@router.post("/reviews", response_model=CreatedReview, status_code=201)
async def create_review(
    channel: str = Form(...),
    title: str = Form("", max_length=200),
    content: str | None = Form(None),
    sample_id: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(require(Permission.submit_content)),
    session: Session = Depends(get_session),
) -> CreatedReview:
    if session.get(ChannelProfile, channel) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown channel '{channel}'.")
    content_uri = None
    try:
        if file is not None and file.filename:
            data = await file.read(5 * 1024 * 1024 + 1)
            doc = from_upload(file.filename, data)
            content_uri = file.filename
        elif sample_id:
            sample = session.get(SampleDraft, sample_id)
            if sample is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown sample.")
            if sample.filename:
                path = get_settings().seed_dir / "files" / sample.filename
                doc = from_upload(sample.filename, path.read_bytes())
                content_uri = sample.filename
            else:
                doc = from_text(sample.content)
            title = title or sample.title
        elif content and content.strip():
            doc = from_text(content, markdown=content.lstrip().startswith("#"))
        else:
            raise IntakeError("Paste some text, upload a file or pick a sample draft.")
    except IntakeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    submission = Submission(
        workspace_id=WORKSPACE_ID,
        author_id=user.id,
        channel=channel,
        title=(title or doc.blocks[0].text[:80]).strip(),
    )
    session.add(submission)
    session.flush()
    revision = _new_revision(session, submission, doc, user, 1, content_uri)
    audit.record(
        session,
        "submission",
        submission.id,
        "created",
        user.id,
        {
            "title": submission.title,
            "channel": channel,
            "revision": revision.id,
            "source": content_uri or "pasted text",
        },
    )
    session.commit()
    runner.start_review(revision.id)
    return CreatedReview(id=submission.id, revision_id=revision.id)


@router.get("/reviews", response_model=list[ReviewListItem])
def list_reviews(
    scope: str = Query("all", pattern="^(all|mine|queue)$"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[ReviewListItem]:
    query = select(Submission).order_by(Submission.updated_at.desc())
    if scope == "mine":
        query = query.where(Submission.author_id == user.id)
    elif scope == "queue":
        query = query.where(Submission.state == SubmissionState.in_review)
    items: list[ReviewListItem] = []
    for submission in session.scalars(query.limit(100)):
        revision = _latest(session, submission)
        findings = _findings(session, revision.id)
        open_findings = [f for f in findings if f.status in ("open", "escalated", "disputed")]
        items.append(
            ReviewListItem(
                id=submission.id,
                title=submission.title,
                channel=submission.channel,
                state=submission.state.value,
                author=UserRef.model_validate(session.get_one(User, submission.author_id)),
                brand_score=revision.brand_score,
                open_criticals=len(blocking_criticals(findings, "approve")),
                open_findings=len(open_findings),
                revision=revision.number,
                review_status=revision.review_status,
                updated_at=submission.updated_at,
            )
        )
    return items


@router.get("/reviews/{review_id}", response_model=ReviewOut)
def get_review(
    review_id: str,
    revision: int | None = None,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ReviewOut:
    submission = _submission(session, review_id)
    latest = _latest(session, submission)
    current = latest
    if revision is not None and revision != latest.number:
        found = session.scalar(
            select(Revision).where(
                Revision.submission_id == submission.id, Revision.number == revision
            )
        )
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Revision not found.")
        current = found
    findings = _findings(session, current.id)
    claims = session.scalars(select(Claim).where(Claim.revision_id == current.id))
    revisions = session.scalars(
        select(Revision).where(Revision.submission_id == submission.id).order_by(Revision.number)
    )
    decisions = session.scalars(
        select(Decision)
        .where(Decision.submission_id == submission.id)
        .order_by(Decision.created_at)
    )
    doc = NormalisedDoc.model_validate(current.normalised_doc)
    return ReviewOut(
        submission=SubmissionOut(
            id=submission.id,
            title=submission.title,
            channel=submission.channel,
            state=submission.state.value,
            author=UserRef.model_validate(session.get_one(User, submission.author_id)),
            approved_by=_user_ref(session.get(User, submission.approved_by or "")),
            approved_at=submission.approved_at,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
        ),
        revision=RevisionOut(
            id=current.id,
            number=current.number,
            brand_score=current.brand_score,
            review_status=current.review_status,
            created_at=current.created_at,
            content=current.content,
            blocks=[b.model_dump() for b in doc.blocks],
            source_format=current.source_format,
            degraded=current.degraded,
            report=current.report,
            completed_at=current.completed_at,
        ),
        revisions=[RevisionSummary.model_validate(r) for r in revisions],
        findings=[_finding_out(f) for f in findings],
        claims=[ClaimOut.model_validate(c) for c in claims],
        decisions=[
            DecisionOut(
                id=d.id,
                kind=d.kind,
                reason=d.reason,
                payload=d.payload,
                finding_id=d.finding_id,
                revision_id=d.revision_id,
                actor=UserRef.model_validate(session.get_one(User, d.actor_id)),
                created_at=d.created_at,
            )
            for d in decisions
        ],
        gate=_gate(submission, latest, _findings(session, latest.id)),
        pending_edits=sum(
            f.status in ("accepted", "edited") for f in _findings(session, latest.id)
        ),
        permissions=permissions_for(user.role),
    )


@router.get("/reviews/{review_id}/events")
async def review_events(
    review_id: str,
    token: str = Query(..., description="Demo JWT (EventSource cannot send headers)"),
    revision: int | None = None,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    try:
        jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.") from exc
    submission = _submission(session, review_id)
    target = _latest(session, submission)
    if revision is not None:
        target = (
            session.scalar(
                select(Revision).where(
                    Revision.submission_id == submission.id, Revision.number == revision
                )
            )
            or target
        )
    key, already_done = target.id, target.review_status in ("complete", "failed")
    bus.bind(asyncio.get_running_loop())

    async def stream() -> AsyncIterator[str]:
        if already_done and not bus.finished(key):
            yield _sse(
                TERMINAL,
                {
                    "ok": target.review_status == "complete",
                    "score": target.brand_score,
                    "degraded": target.degraded,
                },
            )
            return
        history, queue = bus.subscribe(key)
        try:
            for event, data in history:
                yield _sse(event, data)
                if event == TERMINAL:
                    return
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event, data)
                if event == TERMINAL:
                    return
        finally:
            bus.unsubscribe(key, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


# --- decisions on findings -------------------------------------------------------------


@router.post("/findings/{finding_id}/decisions", response_model=DecisionOut, status_code=201)
def decide(
    finding_id: str,
    body: DecisionIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> DecisionOut:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found.")
    revision = session.get_one(Revision, finding.revision_id)
    submission = session.get_one(Submission, revision.submission_id)
    if revision.id != _latest(session, submission).id:
        raise _conflict("This finding belongs to an older revision. Open the latest one.")
    if body.kind == "escalate":
        if not can(user, Permission.escalate):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot escalate findings.")
    else:
        _require_author(user, submission)
    if submission.state not in EDITABLE_STATES and body.kind != "escalate":
        raise _conflict(
            f"The review is {submission.state.value.replace('_', ' ')}; findings "
            "can only be changed on a draft or after changes are requested."
        )

    if body.kind == "accept":
        if not finding.suggestion:
            raise _conflict("This finding has no suggestion to accept. Use Edit instead.")
        finding.status, finding.applied_text = "accepted", str(finding.suggestion["text"])
    elif body.kind == "edit":
        if body.text is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide the edited text.")
        finding.status, finding.applied_text = "edited", body.text
    elif body.kind == "dispute":
        if len(body.reason.strip()) < 5:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A dispute needs a reason (at least 5 characters).",
            )
        finding.status, finding.applied_text = "disputed", None
    elif body.kind == "escalate":
        finding.status, finding.applied_text = "escalated", None
        notify_roles(
            session,
            [Role.reviewer, Role.brand_manager],
            "escalated",
            f'{user.name} escalated {finding.rule_code} on "{submission.title}".',
            submission.id,
            exclude=user.id,
        )
    else:  # reopen
        finding.status, finding.applied_text = "open", None

    decision = Decision(
        submission_id=submission.id,
        revision_id=revision.id,
        finding_id=finding.id,
        kind=body.kind,
        reason=body.reason.strip(),
        actor_id=user.id,
        payload={
            "rule": finding.rule_code,
            "text": finding.text,
            "applied_text": finding.applied_text,
        },
    )
    session.add(decision)
    session.flush()
    audit.record(
        session,
        "finding",
        finding.id,
        f"finding_{body.kind}",
        user.id,
        {
            "submission": submission.id,
            "rule": finding.rule_code,
            "reason": decision.reason,
            "applied_text": finding.applied_text,
        },
    )
    submission.updated_at = utcnow()
    session.commit()
    return DecisionOut(
        id=decision.id,
        kind=decision.kind,
        reason=decision.reason,
        payload=decision.payload,
        finding_id=decision.finding_id,
        revision_id=decision.revision_id,
        actor=UserRef.model_validate(user),
        created_at=decision.created_at,
    )


# --- drafts, re-checks and diffs -------------------------------------------------------


def _draft(session: Session, revision: Revision) -> tuple[str, int]:
    doc = NormalisedDoc.model_validate(revision.normalised_doc)
    blocks, applied = apply_suggestions(
        [b.text for b in doc.blocks], _findings(session, revision.id)
    )
    return "\n\n".join(b for b in blocks if b), applied


@router.get("/reviews/{review_id}/draft", response_model=DraftOut)
def draft_preview(
    review_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> DraftOut:
    revision = _latest(session, _submission(session, review_id))
    content, applied = _draft(session, revision)
    return DraftOut(content=content, applied=applied, changed=content != revision.content)


@router.post("/reviews/{review_id}/revisions", response_model=CreatedReview, status_code=201)
def recheck(
    review_id: str,
    body: RecheckIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> CreatedReview:
    submission = _submission(session, review_id)
    _require_author(user, submission)
    if submission.state not in EDITABLE_STATES:
        raise _conflict("Re-check is available on drafts and after changes are requested.")
    latest = _latest(session, submission)
    if latest.review_status == "pending":
        raise _conflict("Preflight is still checking the current revision.")
    text = body.content if body.content is not None else _draft(session, latest)[0]
    try:
        doc = from_text(text)
    except IntakeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    revision = _new_revision(session, submission, doc, user, latest.number + 1)
    audit.record(
        session,
        "submission",
        submission.id,
        "rechecked",
        user.id,
        {
            "revision": revision.id,
            "number": revision.number,
            "applied_suggestions": sum(
                f.status in ("accepted", "edited") for f in _findings(session, latest.id)
            ),
        },
    )
    submission.updated_at = utcnow()
    session.commit()
    runner.start_review(revision.id)
    return CreatedReview(id=submission.id, revision_id=revision.id)


@router.get("/reviews/{review_id}/diff", response_model=DiffOut)
def diff(
    review_id: str,
    from_number: int = Query(..., alias="from"),
    to_number: int = Query(..., alias="to"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> DiffOut:
    submission = _submission(session, review_id)
    revs = {
        r.number: r
        for r in session.scalars(select(Revision).where(Revision.submission_id == submission.id))
    }
    if from_number not in revs or to_number not in revs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revision not found.")
    a, b = revs[from_number], revs[to_number]
    fa, fb = _findings(session, a.id), _findings(session, b.id)
    keys_b = {(f.rule_code, f.text) for f in fb}
    keys_a = {(f.rule_code, f.text) for f in fa}
    return DiffOut(
        from_number=from_number,
        to_number=to_number,
        from_text=a.content,
        to_text=b.content,
        from_score=a.brand_score,
        to_score=b.brand_score,
        resolved=[_finding_out(f) for f in fa if (f.rule_code, f.text) not in keys_b],
        introduced=[_finding_out(f) for f in fb if (f.rule_code, f.text) not in keys_a],
    )


# --- workflow transitions --------------------------------------------------------------


@router.post("/reviews/{review_id}/transition", response_model=ReviewOut)
def transition(
    review_id: str,
    body: TransitionIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ReviewOut:
    submission = _submission(session, review_id)
    try:
        rule = check_transition(submission.state, body.action)
    except TransitionError as exc:
        raise _conflict(str(exc)) from exc
    if not can(user, rule.permission):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Your role cannot {body.action.replace('_', ' ')} content."
        )
    if body.action == "submit":
        _require_author(user, submission)
    latest = _latest(session, submission)
    if latest.review_status != "complete":
        raise _conflict("Wait for Preflight to finish checking the latest revision.")
    findings = _findings(session, latest.id)

    if body.action == "submit":
        blocking = blocking_criticals(findings, "submit")
        if blocking:
            raise _conflict(
                "Fix, dispute or escalate the critical findings before submitting.",
                blocking=[f.id for f in blocking],
            )
    if body.action == "request_changes" and not body.comment.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tell the author what to change.")
    if body.action == "approve":
        _apply_overrides(session, submission, latest, findings, body, user)
        submission.approved_by, submission.approved_at = user.id, utcnow()

    previous = submission.state
    submission.state = rule.target
    submission.updated_at = utcnow()
    if body.comment.strip():
        session.add(Comment(submission_id=submission.id, author_id=user.id, body=body.comment))
    session.add(
        Decision(
            submission_id=submission.id,
            revision_id=latest.id,
            kind=body.action,
            reason=body.comment.strip(),
            actor_id=user.id,
            payload={
                "from": previous.value,
                "to": rule.target.value,
                "brand_score": latest.brand_score,
            },
        )
    )
    audit.record(
        session,
        "submission",
        submission.id,
        body.action,
        user.id,
        {
            "from": previous.value,
            "to": rule.target.value,
            "revision": latest.id,
            "brand_score": latest.brand_score,
            "overrides": [o.model_dump() for o in body.overrides],
        },
    )
    _notify_transition(session, submission, body.action, user)
    session.commit()
    return get_review(review_id, None, user, session)


def _apply_overrides(
    session: Session,
    submission: Submission,
    revision: Revision,
    findings: list[Finding],
    body: TransitionIn,
    user: User,
) -> None:
    blocking = {f.id: f for f in blocking_criticals(findings, "approve")}
    overrides = {o.finding_id: o for o in body.overrides}
    missing = [fid for fid in blocking if fid not in overrides]
    if missing:
        raise _conflict(
            "Critical findings are unresolved. Override each one with a written reason, or "
            "request changes.",
            blocking=missing,
        )
    for fid, override in overrides.items():
        finding = blocking.get(fid)
        if finding is None:
            continue
        finding.status = "resolved"
        session.add(
            Decision(
                submission_id=submission.id,
                revision_id=revision.id,
                finding_id=fid,
                kind="override",
                reason=override.reason,
                actor_id=user.id,
                payload={"rule": finding.rule_code, "text": finding.text, "severity": "critical"},
            )
        )
        audit.record(
            session,
            "finding",
            fid,
            "finding_override",
            user.id,
            {"submission": submission.id, "rule": finding.rule_code, "reason": override.reason},
        )


def _notify_transition(session: Session, submission: Submission, action: str, user: User) -> None:
    title = submission.title
    if action == "submit":
        notify_roles(
            session,
            [Role.approver, Role.brand_manager],
            "submitted",
            f'{user.name} submitted "{title}" for approval.',
            submission.id,
            exclude=user.id,
        )
    elif action == "request_changes":
        notify_users(
            session,
            [submission.author_id],
            "changes_requested",
            f'{user.name} requested changes on "{title}".',
            submission.id,
        )
    elif action == "approve":
        notify_users(
            session,
            [submission.author_id],
            "approved",
            f'{user.name} approved "{title}". The Review Receipt is ready.',
            submission.id,
        )


# --- comments --------------------------------------------------------------------------


@router.get("/reviews/{review_id}/comments", response_model=list[CommentOut])
def list_comments(
    review_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[CommentOut]:
    _submission(session, review_id)
    comments = session.scalars(
        select(Comment).where(Comment.submission_id == review_id).order_by(Comment.created_at)
    )
    return [
        CommentOut(
            id=c.id,
            body=c.body,
            finding_id=c.finding_id,
            created_at=c.created_at,
            author=UserRef.model_validate(session.get_one(User, c.author_id)),
        )
        for c in comments
    ]


@router.post("/reviews/{review_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    review_id: str,
    body: CommentIn,
    user: User = Depends(require(Permission.comment)),
    session: Session = Depends(get_session),
) -> CommentOut:
    submission = _submission(session, review_id)
    comment = Comment(
        submission_id=submission.id,
        finding_id=body.finding_id,
        author_id=user.id,
        body=body.body.strip(),
    )
    session.add(comment)
    session.flush()
    audit.record(
        session,
        "comment",
        comment.id,
        "commented",
        user.id,
        {"submission": submission.id, "finding": body.finding_id},
    )
    if user.id != submission.author_id:
        notify_users(
            session,
            [submission.author_id],
            "comment",
            f'{user.name} commented on "{submission.title}".',
            submission.id,
        )
    session.commit()
    return CommentOut(
        id=comment.id,
        body=comment.body,
        finding_id=comment.finding_id,
        created_at=comment.created_at,
        author=UserRef.model_validate(user),
    )
