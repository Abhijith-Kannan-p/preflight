"""Demo sign-in (role switcher), notifications and the audit log."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit
from app.auth import current_user, issue_token, permissions_for
from app.config import get_settings
from app.db import get_session
from app.models import AuditEvent, Notification, SampleDraft, User
from app.schemas.reviews import NotificationOut, UserRef

router = APIRouter(prefix="/api", tags=["session"])


class DemoLoginIn(BaseModel):
    user_id: str


class SessionOut(BaseModel):
    token: str
    user: UserRef
    permissions: list[str]


@router.post("/auth/demo-login", response_model=SessionOut)
def demo_login(body: DemoLoginIn, session: Session = Depends(get_session)) -> SessionOut:
    """Demo mode: no passwords. Each seeded PayWise user can be picked from the header."""
    user = session.get(User, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user.")
    return SessionOut(
        token=issue_token(user),
        user=UserRef.model_validate(user),
        permissions=permissions_for(user.role),
    )


@router.get("/auth/me", response_model=SessionOut)
def me(user: User = Depends(current_user)) -> SessionOut:
    return SessionOut(
        token=issue_token(user),
        user=UserRef.model_validate(user),
        permissions=permissions_for(user.role),
    )


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


@router.post("/notifications/read", status_code=204)
def mark_read(user: User = Depends(current_user), session: Session = Depends(get_session)) -> None:
    session.execute(update(Notification).where(Notification.user_id == user.id).values(read=True))
    session.commit()


@router.get("/audit/verify", response_model=audit.ChainStatus)
def verify_audit(session: Session = Depends(get_session)) -> audit.ChainStatus:
    """Recompute every hash in the audit chain. Public, so anyone can check a receipt."""
    return audit.verify_chain(session)


@router.get("/audit")
def audit_trail(
    entity_id: str | None = None,
    limit: int = 100,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, 500))
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
def sample_file(sample_id: str, session: Session = Depends(get_session)) -> FileResponse:
    sample = session.get(SampleDraft, sample_id)
    if sample is None or not sample.filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This sample has no file.")
    return FileResponse(
        get_settings().seed_dir / "files" / sample.filename, filename=sample.filename
    )
