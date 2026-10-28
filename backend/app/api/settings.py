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
from app.auth import Permission, current_user, issue_token, permissions_for, require
from app.config import get_settings
from app.db import get_session
from app.ml.embeddings import get_embedder
from app.models import (
    SANDBOX_KIND,
    ApiKey,
    User,
    Webhook,
    WebhookDelivery,
    Workspace,
    utcnow,
)
from app.seed import seed_all
from app.services import sandbox
from app.services.history import ensure_demo_history
from app.services.webhooks import EVENTS, WebhookEvent, deliver

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
    workspace = session.get_one(Workspace, user.workspace_id)
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
    workspace = session.get_one(Workspace, user.workspace_id)
    workspace.settings = {**workspace.settings, "masking_enabled": body.enabled}
    audit.record(
        session, "workspace", workspace.id, "masking_changed", user.id, {"enabled": body.enabled}
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
    keys = select(ApiKey).where(ApiKey.workspace_id == user.workspace_id)
    return [_key_out(k) for k in session.scalars(keys.order_by(ApiKey.created_at.desc()))]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
def create_key(
    body: ApiKeyIn, user: User = Depends(admin), session: Session = Depends(get_session)
) -> dict[str, Any]:
    raw = KEY_PREFIX + secrets.token_urlsafe(24)
    key = ApiKey(
        workspace_id=user.workspace_id,
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
    if key is None or key.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found.")
    key.revoked_at = utcnow()
    audit.record(session, "api_key", key_id, "api_key_revoked", user.id, {})
    session.commit()


# --- webhooks --------------------------------------------------------------------------


class WebhookIn(BaseModel):
    url: HttpUrl
    slack_format: bool = False
    events: list[WebhookEvent] = Field(default_factory=lambda: list(EVENTS), min_length=1)


class WebhookPatch(BaseModel):
    events: list[WebhookEvent] = Field(min_length=1)


class DeliveryOut(BaseModel):
    id: int
    event: str
    status: str
    status_code: int | None
    latency_ms: int
    ok: bool
    error: str | None
    attempts: int
    attempt_log: list[dict[str, Any]]
    resent_from: int | None
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
        for w in session.scalars(
            select(Webhook)
            .where(Webhook.workspace_id == user.workspace_id)
            .order_by(Webhook.created_at)
        )
    ]


@router.post("/webhooks", response_model=WebhookOut, status_code=201)
def create_webhook(
    body: WebhookIn, user: User = Depends(admin), session: Session = Depends(get_session)
) -> WebhookOut:
    webhook = Webhook(
        workspace_id=user.workspace_id,
        url=str(body.url),
        slack_format=body.slack_format,
        secret=secrets.token_hex(24),
        events=list(dict.fromkeys(body.events)),
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
    if webhook is None or webhook.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    session.execute(delete(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id))
    session.delete(webhook)
    audit.record(session, "webhook", webhook_id, "webhook_deleted", user.id, {})
    session.commit()


def _own_webhook(session: Session, user: User, webhook_id: str) -> Webhook:
    webhook = session.get(Webhook, webhook_id)
    if webhook is None or webhook.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    return webhook


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    webhook_id: str,
    body: WebhookPatch,
    user: User = Depends(admin),
    session: Session = Depends(get_session),
) -> WebhookOut:
    webhook = _own_webhook(session, user, webhook_id)
    webhook.events = list(dict.fromkeys(body.events))
    audit.record(
        session, "webhook", webhook.id, "webhook_updated", user.id, {"events": webhook.events}
    )
    session.commit()
    return _webhook_out(session, webhook)


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryOut)
def test_webhook(
    webhook_id: str, user: User = Depends(admin), session: Session = Depends(get_session)
) -> DeliveryOut:
    """One sample `submission.approved` event. Returns after the first attempt; retries, if
    any, continue in the background and show up in the delivery log."""
    webhook = _own_webhook(session, user, webhook_id)
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
    delivery = deliver(session, webhook, event, wait=False)
    return DeliveryOut.model_validate(delivery, from_attributes=True)


@router.post("/webhooks/{webhook_id}/deliveries/{delivery_id}/resend", response_model=DeliveryOut)
def resend_delivery(
    webhook_id: str,
    delivery_id: int,
    user: User = Depends(admin),
    session: Session = Depends(get_session),
) -> DeliveryOut:
    """Send the same event again as a new delivery (with its own retries)."""
    webhook = _own_webhook(session, user, webhook_id)
    original = session.get(WebhookDelivery, delivery_id)
    if original is None or original.webhook_id != webhook.id or not original.payload:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found or not resendable.")
    delivery = deliver(session, webhook, original.payload, resent_from=original.id, wait=False)
    audit.record(
        session,
        "webhook",
        webhook.id,
        "webhook_resent",
        user.id,
        {"delivery": original.id, "event": original.event},
    )
    session.commit()
    return DeliveryOut.model_validate(delivery, from_attributes=True)


# --- demo reset ------------------------------------------------------------------------


class ResetOut(BaseModel):
    token: str
    user_id: str
    permissions: list[str]


@router.post("/reset-demo", response_model=ResetOut)
def reset_demo(user: User = Depends(admin), session: Session = Depends(get_session)) -> ResetOut:
    """Reset the caller's workspace to the PayWise starting state: brand, personas, review
    history and a fresh audit chain. In a demo sandbox only that visitor's copy is touched.
    Keys and webhooks are removed. Returns a new token, because personas get new ids."""
    workspace = session.get_one(Workspace, user.workspace_id)
    persona = user.persona or user.id
    if workspace.kind == SANDBOX_KIND:
        sandbox.reset_sandbox(session, workspace.id)
    else:
        sandbox.clear_workspace(session, workspace.id)
        workspace.rulebook_version += 1
        workspace.factbook_version += 1
        session.flush()
        seed_all(session, get_settings().seed_dir, get_embedder())
        if get_settings().bootstrap_demo:
            threading.Thread(target=ensure_demo_history, daemon=True, name="demo-history").start()
    member = sandbox.find_user(session, workspace.id, persona)
    if member is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Reset left no demo users.")
    audit.record(session, "workspace", workspace.id, "demo_reset", member.id, {})
    session.commit()
    return ResetOut(
        token=issue_token(member), user_id=member.id, permissions=permissions_for(member.role)
    )
