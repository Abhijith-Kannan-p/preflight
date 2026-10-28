"""Rulebook Compiler: brand book in, reviewed rules out."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Permission, current_user, require
from app.compiler import pipeline
from app.compiler.apply import apply
from app.compiler.schema import validate
from app.config import get_settings
from app.db import get_session
from app.models import CompileJob, RuleCandidate, User, utcnow
from app.services.events import TERMINAL, bus

router = APIRouter(prefix="/api/compiler", tags=["rulebook compiler"])
editor = require(Permission.edit_rulebook)
MAX_BYTES = 5 * 1024 * 1024
SAMPLE_NAME = "paywise_brand_book.pdf"


def _sample_path() -> Any:
    return get_settings().data_dir / "samples" / SAMPLE_NAME


def _job(session: Session, job_id: str, workspace_id: str) -> CompileJob:
    job = session.get(CompileJob, job_id)
    if job is None or job.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compile job not found.")
    return job


@router.get("/sample")
def sample_brand_book() -> FileResponse:
    """The fictional PayWise Brand Book the compiler is demonstrated on."""
    return FileResponse(_sample_path(), media_type="application/pdf", filename=SAMPLE_NAME)


@router.post("/jobs", status_code=201)
async def start_job(
    file: UploadFile | None = File(None),
    use_sample: bool = Form(False),
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if use_sample:
        data, filename = _sample_path().read_bytes(), SAMPLE_NAME
    elif file is not None and file.filename:
        filename = file.filename
        if not filename.lower().endswith((".pdf", ".docx")):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a brand book as PDF or DOCX."
            )
        data = await file.read(MAX_BYTES + 1)
        if not data:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This file is empty.")
        if len(data) > MAX_BYTES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Brand books must be 5 MB or smaller."
            )
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a brand book or use the sample."
        )
    job = CompileJob(workspace_id=user.workspace_id, filename=filename, created_by=user.id)
    session.add(job)
    session.commit()
    pipeline.start(job.id, data, filename)
    return {"id": job.id}


@router.get("/jobs")
def list_jobs(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    jobs = session.scalars(
        select(CompileJob)
        .where(CompileJob.workspace_id == user.workspace_id)
        .order_by(CompileJob.created_at.desc())
        .limit(10)
    )
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "status": j.status,
            "created_at": j.created_at,
            "report": j.report,
        }
        for j in jobs
    ]


def _candidate_out(c: RuleCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "kind": c.kind,
        "key": c.key,
        "payload": c.payload,
        "extracted": c.extracted,
        "source_page": c.source_page,
        "excerpt": c.excerpt,
        "origin": c.origin,
        "match_status": c.match_status,
        "match_ref": c.match_ref,
        "match_note": c.match_note,
        "decision": c.decision,
        "applied_ref": c.applied_ref,
    }


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    job = _job(session, job_id, user.workspace_id)
    order = {"new": 0, "update": 1, "duplicate": 2}
    candidates = sorted(
        session.scalars(select(RuleCandidate).where(RuleCandidate.job_id == job.id)),
        key=lambda c: (order.get(c.match_status, 3), c.source_page, c.kind),
    )
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "created_at": job.created_at,
        "report": job.report,
        "summary": pipeline.summary(job, candidates),
        "stages": [{"stage": s, "label": label} for s, label in pipeline.STAGES],
        "candidates": [_candidate_out(c) for c in candidates],
    }


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str, token: str = Query(...), session: Session = Depends(get_session)
) -> StreamingResponse:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.") from exc
    viewer = session.get(User, claims.get("sub"))
    if viewer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user.")
    job = _job(session, job_id, viewer.workspace_id)
    finished = job.status != "running"
    bus.bind(asyncio.get_running_loop())

    async def stream() -> AsyncIterator[str]:
        import json

        def sse(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

        if finished and not bus.finished(job_id):
            yield sse(TERMINAL, {"ok": job.status == "ready", **(job.report or {})})
            return
        history, queue = bus.subscribe(job_id)
        try:
            for event, data in history:
                yield sse(event, data)
                if event == TERMINAL:
                    return
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield sse(event, data)
                if event == TERMINAL:
                    return
        finally:
            bus.unsubscribe(job_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class DecisionIn(BaseModel):
    action: Literal["accept", "reject"]
    # An edited payload; omitted means "as extracted".
    payload: dict[str, Any] | None = None


@router.post("/candidates/{candidate_id}/decision")
def decide(
    candidate_id: str,
    body: DecisionIn,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    candidate = session.get(RuleCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found.")
    job = _job(session, candidate.job_id, user.workspace_id)
    if candidate.decision != "pending":
        return _candidate_out(candidate)  # deciding twice changes nothing
    if body.action == "reject":
        candidate.decision = "rejected"
    else:
        payload = candidate.payload
        if body.payload is not None:
            checked = validate(candidate.kind, body.payload)
            if checked is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "The edited rule does not fit its schema."
                )
            payload = checked
        candidate.applied_ref = apply(
            session, user, candidate.kind, payload, job.filename, candidate.source_page
        )
        candidate.decision = "edited" if payload != candidate.extracted else "accepted"
        candidate.payload = payload
    candidate.decided_by, candidate.decided_at = user.id, utcnow()
    session.commit()
    return _candidate_out(candidate)
