"""Workspace settings: API keys, webhooks, AI and privacy settings, demo reset. Admin only,
except reading the AI status, which every signed-in user can see."""

import hashlib
import secrets
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.ai.gateway import get_gateway
from app.auth import Permission, current_user, require
from app.config import get_settings
from app.db import get_session
from app.ml.embeddings import get_embedder
from app.models import (
    AiCall,
    ApiKey,
    AuditEvent,
    ChannelProfile,
    Claim,
    Comment,
    ConfidentialTerm,
    Decision,
    Fact,
    Finding,
    Notification,
    Revision,
    Rule,
    SampleDraft,
    Submission,
    Term,
    User,
    Webhook,
    WebhookDelivery,
    Workspace,
    utcnow,
)
from app.seed import WORKSPACE_ID, seed_all
from app.services.history import ensure_demo_history
from app.services.webhooks import deliver

router = APIRouter(prefix="/api/settings", tags=["settings"])
admin = require(Permission.administer)

KEY_PREFIX = "pf_live_"


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- AI and privacy --------------------------------------------------------------------


class AiStatus(BaseModel):
    provider: str
    model: str | None
    mode: str
    masking_enabled: bool
    timeout_seconds: float


@router.get("/ai", response_model=AiStatus)
def ai_status(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> AiStatus:
    gateway = get_gateway()
    workspace = session.get_one(Workspace, WORKSPACE_ID)
    settings = get_settings()
    return AiStatus(
        provider=gateway.provider.name if gateway.provider else "none",
        model=gateway.provider.model if gateway.provider else None,
        mode=gateway.mode,
        masking_enabled=bool(workspace.settings.get("masking_enabled", settings.masking_enabled)),
        timeout_seconds=settings.llm_timeout_seconds,
    )


class MaskingIn(BaseModel):
    enabled: bool


@router.put("/masking", response_model=AiStatus)
def set_masking(
    body: MaskingIn, user: User = Depends(admin), session: Session = Depends(get_session)
) -> AiStatus:
    workspace = session.get_one(Workspace, WORKSPACE_ID)
    workspace.settings = {**workspace.settings, "masking_enabled": body.enabled}
    audit.record(
        session, "workspace", WORKSPACE_ID, "masking_changed", user.id, {"enabled": body.enabled}
    )
    session.commit()
    return ai_status(user, session)


# --- API keys --------------------------------------------------------------------------


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown once. Store it securely.")


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


def _key_out(k: ApiKey) -> dict[str, Any]:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
        "revoked_at": k.revoked_at,
    }


@router.get("/keys", response_model=list[ApiKeyOut])
def list_keys(
    user: User = Depends(admin), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    return [_key_out(k) for k in session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
def create_key(
    body: ApiKeyIn, user: User = Depends(admin), session: Session = Depends(get_session)
) -> dict[str, Any]:
    raw = KEY_PREFIX + secrets.token_urlsafe(24)
    key = ApiKey(
        workspace_id=WORKSPACE_ID,
        name=body.name,
        prefix=raw[:12],
        key_hash=hash_key(raw),
        created_by=user.id,
    )
    session.add(key)
    session.flush()
    audit.record(session, "api_key", key.id, "api_key_created", user.id, {"name": body.name})
    session.commit()
    return {**_key_out(key), "key": raw}


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(
    key_id: str, user: User = Depends(admin), session: Session = Depends(get_session)
) -> None:
    key = session.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found.")
    key.revoked_at = utcnow()
    audit.record(session, "api_key", key_id, "api_key_revoked", user.id, {})
    session.commit()


# --- webhooks --------------------------------------------------------------------------


class WebhookIn(BaseModel):
    url: HttpUrl
    slack_format: bool = False


class DeliveryOut(BaseModel):
    id: int
    event: str
    status_code: int | None
    latency_ms: int
    ok: bool
    error: str | None
    created_at: datetime


class WebhookOut(BaseModel):
    id: str
    url: str
    slack_format: bool
    events: list[str]
    active: bool
    secret: str
    deliveries: list[DeliveryOut]


def _webhook_out(session: Session, w: Webhook) -> WebhookOut:
    deliveries = session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == w.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(10)
    )
    return WebhookOut(
        id=w.id,
        url=w.url,
        slack_format=w.slack_format,
        events=w.events,
        active=w.active,
        secret=w.secret,
        deliveries=[DeliveryOut.model_validate(d, from_attributes=True) for d in deliveries],
    )


@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(
    user: User = Depends(admin), session: Session = Depends(get_session)
) -> list[WebhookOut]:
    return [
        _webhook_out(session, w)
        for w in session.scalars(select(Webhook).order_by(Webhook.created_at))
    ]


@router.post("/webhooks", response_model=WebhookOut, status_code=201)
def create_webhook(
    body: WebhookIn, user: User = Depends(admin), session: Session = Depends(get_session)
) -> WebhookOut:
    webhook = Webhook(
        workspace_id=WORKSPACE_ID,
        url=str(body.url),
        slack_format=body.slack_format,
        secret=secrets.token_hex(24),
        events=["submission.approved"],
    )
    session.add(webhook)
    session.flush()
    audit.record(session, "webhook", webhook.id, "webhook_created", user.id, {"url": str(body.url)})
    session.commit()
    return _webhook_out(session, webhook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(
    webhook_id: str, user: User = Depends(admin), session: Session = Depends(get_session)
) -> None:
    webhook = session.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    session.execute(delete(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id))
    session.delete(webhook)
    audit.record(session, "webhook", webhook_id, "webhook_deleted", user.id, {})
    session.commit()


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryOut)
def test_webhook(
    webhook_id: str, user: User = Depends(admin), session: Session = Depends(get_session)
) -> DeliveryOut:
    webhook = session.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    event = {
        "event": "submission.approved",
        "test": True,
        "submission": {
            "id": "sub_test",
            "title": "Test event from Preflight",
            "channel": "linkedin",
            "state": "approved",
        },
        "brand_score": 97,
        "approved_by": user.name,
        "approved_at": utcnow().isoformat(),
        "receipt_url": f"{get_settings().public_app_url.rstrip('/')}/receipt/sub_test",
    }
    delivery = deliver(session, webhook, event)
    return DeliveryOut.model_validate(delivery, from_attributes=True)


# --- demo reset ------------------------------------------------------------------------


@router.post("/reset-demo", status_code=204)
def reset_demo(user: User = Depends(admin), session: Session = Depends(get_session)) -> None:
    """Delete every review and its history, restore the PayWise brand, start a fresh audit
    chain. Keys and webhooks are kept."""
    for model in (WebhookDelivery, Notification, AiCall, Comment, Decision, Claim, Finding):
        session.execute(delete(model))
    session.execute(delete(Revision))
    session.execute(delete(Submission))
    session.execute(delete(AuditEvent))
    for brand_model in (Rule, Fact, Term, ConfidentialTerm, ChannelProfile, SampleDraft):
        session.execute(delete(brand_model))
    workspace = session.get_one(Workspace, WORKSPACE_ID)
    workspace.rulebook_version += 1
    workspace.factbook_version += 1
    session.flush()
    seed_all(session, get_settings().seed_dir, get_embedder())
    audit.record(session, "workspace", WORKSPACE_ID, "demo_reset", user.id, {})
    session.commit()
    if get_settings().bootstrap_demo:
        threading.Thread(target=ensure_demo_history, daemon=True, name="demo-history").start()
