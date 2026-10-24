"""Outgoing webhooks, signed with HMAC-SHA256, with an optional Slack-compatible payload.

Header: X-Preflight-Signature: sha256=<hex hmac of the raw body, keyed by the webhook secret>
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Revision, Submission, User, Webhook, WebhookDelivery, utcnow

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5.0


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(secret, body), signature)


def approval_event(session: Session, submission: Submission) -> dict[str, Any]:
    revision = session.scalar(
        select(Revision)
        .where(Revision.submission_id == submission.id)
        .order_by(Revision.number.desc())
        .limit(1)
    )
    approver = session.get(User, submission.approved_by or "")
    receipt = f"{get_settings().public_app_url.rstrip('/')}/receipt/{submission.id}"
    return {
        "event": "submission.approved",
        "submission": {
            "id": submission.id,
            "title": submission.title,
            "channel": submission.channel,
            "state": submission.state.value,
        },
        "brand_score": revision.brand_score if revision else None,
        "approved_by": approver.name if approver else None,
        "approved_at": (submission.approved_at or utcnow()).isoformat(),
        "receipt_url": receipt,
    }


def slack_payload(event: dict[str, Any]) -> dict[str, Any]:
    sub = event["submission"]
    text = (
        f":white_check_mark: *{sub['title']}* ({sub['channel']}) was approved by "
        f"{event['approved_by']} with Brand Score {event['brand_score']}. "
        f"<{event['receipt_url']}|View the Review Receipt>"
    )
    return {"text": text, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}


def deliver(session: Session, webhook: Webhook, event: dict[str, Any]) -> WebhookDelivery:
    payload = slack_payload(event) if webhook.slack_format else event
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Preflight-Webhooks/1.0",
        "X-Preflight-Event": event["event"],
        "X-Preflight-Signature": sign(webhook.secret, body),
    }
    started = time.perf_counter()
    status_code: int | None = None
    error: str | None = None
    try:
        response = httpx.post(webhook.url, content=body, headers=headers, timeout=TIMEOUT_SECONDS)
        status_code = response.status_code
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event=event["event"],
        status_code=status_code,
        latency_ms=int((time.perf_counter() - started) * 1000),
        ok=status_code is not None and 200 <= status_code < 300,
        error=error,
    )
    session.add(delivery)
    session.commit()
    return delivery


def dispatch_approval(submission_id: str) -> None:
    """Fire-and-forget delivery to every active webhook subscribed to approvals."""

    def run() -> None:
        with SessionLocal() as session:
            submission = session.get(Submission, submission_id)
            if submission is None:
                return
            event = approval_event(session, submission)
            for webhook in session.scalars(select(Webhook).where(Webhook.active.is_(True))):
                if "submission.approved" in webhook.events:
                    try:
                        deliver(session, webhook, event)
                    except Exception:
                        log.exception("webhook %s failed", webhook.id)

    threading.Thread(target=run, daemon=True, name=f"webhook-{submission_id}").start()
