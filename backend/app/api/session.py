"""Demo sign-in (role switcher), notifications and the audit log."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit
from app.auth import (
    current_user,
    current_workspace_id,
    issue_token,
    permissions_for,
    user_from_query_token,
)
from app.config import get_settings
from app.db import get_session
from app.models import TEMPLATE_WORKSPACE_ID, AuditEvent, Notification, User
from app.schemas.reviews import NotificationOut, UserRef
from app.scoped import get_sample
from app.services import sandbox
from app.services.events import bus
from app.services.notify import stream_key

router = APIRouter(prefix="/api", tags=["session"])


class DemoLoginIn(BaseModel):
    user_id: str


class SessionOut(BaseModel):
    token: str
    user: UserRef
    permissions: list[str]
    workspace_id: str


def session_out(user: User) -> SessionOut:
    return SessionOut(
        token=issue_token(user),
        user=UserRef.model_validate(user),
        permissions=permissions_for(user.role),
        workspace_id=user.workspace_id,
    )


@router.post("/auth/demo-login", response_model=SessionOut)
def demo_login(
    body: DemoLoginIn,
    pf_sandbox: str | None = Cookie(None),
    session: Session = Depends(get_session),
) -> SessionOut:
    """Demo mode: no passwords. Signs in as a demo persona (`usr_abhi1` to `usr_abhi5`) in the
    caller's sandbox when the sandbox cookie is present, otherwise in the shared template.
    The web app uses `POST /api/sandbox/session`, which also creates the sandbox."""
    live = sandbox.live_sandbox(session, pf_sandbox)
    user = sandbox.find_user(session, live.id if live else TEMPLATE_WORKSPACE_ID, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user.")
    return session_out(user)


@router.get("/auth/me", response_model=SessionOut)
def me(user: User = Depends(current_user)) -> SessionOut:
    return session_out(user)


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(30)
        )
    )


@router.get("/notifications/stream")
async def notification_stream(
    token: str = Query(..., description="Demo JWT (EventSource cannot send headers)"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """New notifications as they are created (`event: notification`); the client then
    refetches the list. Live only: nothing is replayed, the list endpoint is the history."""
    user = user_from_query_token(token, session)
    key = stream_key(user.id)
    bus.bind(asyncio.get_running_loop())

    async def stream() -> AsyncIterator[str]:
        _history, queue = bus.subscribe(key)
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                try:
                    name, data = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"
        finally:
            bus.unsubscribe(key, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/notifications/read", status_code=204)
def mark_read(user: User = Depends(current_user), session: Session = Depends(get_session)) -> None:
    session.execute(update(Notification).where(Notification.user_id == user.id).values(read=True))
    session.commit()


@router.get("/audit/verify", response_model=audit.ChainStatus)
def verify_audit(
    ws: str = Depends(current_workspace_id), session: Session = Depends(get_session)
) -> audit.ChainStatus:
    """Recompute every hash in the caller's audit chain (signed out: the template's)."""
    return audit.verify_chain(session, ws)


@router.get("/audit")
def audit_trail(
    entity_id: str | None = None,
    limit: int = 100,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = (
        select(AuditEvent)
        .where(AuditEvent.workspace_id == user.workspace_id)
        .order_by(AuditEvent.id.desc())
        .limit(min(limit, 500))
    )
    if entity_id:
        query = query.where(
            (AuditEvent.entity_id == entity_id)
            | (AuditEvent.payload_json["submission"].as_string() == entity_id)
        )
    return [
        {
            "id": e.id,
            "entity": e.entity,
            "entity_id": e.entity_id,
            "action": e.action,
            "actor_id": e.actor_id,
            "payload": e.payload_json,
            "ts": e.ts,
            "hash": e.hash,
            "prev_hash": e.prev_hash,
        }
        for e in session.scalars(query)
    ]


@router.get("/samples/{sample_id}/file")
def sample_file(
    sample_id: str, ws: str = Depends(current_workspace_id), session: Session = Depends(get_session)
) -> FileResponse:
    sample = get_sample(session, ws, sample_id)
    if sample is None or not sample.filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This sample has no file.")
    return FileResponse(
        get_settings().seed_dir / "files" / sample.filename, filename=sample.filename
    )
