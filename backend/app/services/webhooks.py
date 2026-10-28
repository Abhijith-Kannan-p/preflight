"""Outgoing webhooks, signed with HMAC-SHA256, with an optional Slack-compatible payload.

Header: X-Preflight-Signature: sha256=<hex hmac of the raw body, keyed by the webhook secret>

Events:
- submission.approved: an approver cleared a submission;
- review.published: a cleared submission was marked as published;
- finding.critical: a review finished with at least one confident critical finding.

Delivery: up to 3 attempts with exponential backoff (2 s, then 4 s). Network errors, 5xx,
408 and 429 are retried; any other 4xx is final. Each delivery is one row whose attempt_log
holds every try; a delivery can be resent as a new row (`resent_from`).
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Finding,
    Revision,
    Severity,
    Submission,
    User,
    Webhook,
    WebhookDelivery,
    utcnow,
)

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5.0
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
WebhookEvent = Literal["submission.approved", "review.published", "finding.critical"]
EVENTS: tuple[WebhookEvent, ...] = ("submission.approved", "review.published", "finding.critical")

# Tests point this at the test database.
session_factory: Callable[[], Session] = SessionLocal


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(secret, body), signature)


# --- events -------------------------------------------------------------------------------


def _app_url(path: str) -> str:
    return f"{get_settings().public_app_url.rstrip('/')}{path}"


def _latest(session: Session, submission: Submission) -> Revision | None:
    return session.scalar(
        select(Revision)
        .where(Revision.submission_id == submission.id)
        .order_by(Revision.number.desc())
        .limit(1)
    )


def _submission(submission: Submission) -> dict[str, Any]:
    return {
        "id": submission.id,
        "title": submission.title,
        "channel": submission.channel,
        "state": submission.state.value,
    }


def approval_event(session: Session, submission: Submission) -> dict[str, Any]:
    revision = _latest(session, submission)
    approver = session.get(User, submission.approved_by or "")
    return {
        "event": "submission.approved",
        "submission": _submission(submission),
        "brand_score": revision.brand_score if revision else None,
        "approved_by": approver.name if approver else None,
        "approved_at": (submission.approved_at or utcnow()).isoformat(),
        "receipt_url": _app_url(f"/receipt/{submission.id}"),
    }


def published_event(session: Session, submission: Submission, user: User) -> dict[str, Any]:
    revision = _latest(session, submission)
    return {
        "event": "review.published",
        "submission": _submission(submission),
        "brand_score": revision.brand_score if revision else None,
        "published_by": user.name,
        "published_at": utcnow().isoformat(),
        "receipt_url": _app_url(f"/receipt/{submission.id}"),
    }


def critical_event(session: Session, revision: Revision) -> dict[str, Any] | None:
    findings = session.scalars(
        select(Finding).where(
            Finding.revision_id == revision.id,
            Finding.severity == Severity.critical,
            Finding.needs_review.is_(False),
        )
    ).all()
    if not findings:
        return None
    submission = revision.submission
    return {
        "event": "finding.critical",
        "submission": _submission(submission),
        "revision": revision.number,
        "brand_score": revision.brand_score,
        "findings": [
            {
                "rule": f.rule_code,
                "source": f.rule_source,
                "text": f.text,
                "explanation": f.explanation,
            }
            for f in findings
        ],
        "review_url": _app_url(f"/app/review/{submission.id}"),
    }


def slack_payload(event: dict[str, Any]) -> dict[str, Any]:
    sub = event["submission"]
    if event["event"] == "finding.critical":
        rules = ", ".join(sorted({f["rule"] for f in event["findings"]}))
        text = (
            f":rotating_light: *{sub['title']}* ({sub['channel']}) has "
            f"{len(event['findings'])} critical finding(s): {rules}. "
            f"<{event['review_url']}|Open the review>"
        )
    elif event["event"] == "review.published":
        text = (
            f":rocket: *{sub['title']}* ({sub['channel']}) was marked as published by "
            f"{event['published_by']}. <{event['receipt_url']}|View the Review Receipt>"
        )
    else:
        text = (
            f":white_check_mark: *{sub['title']}* ({sub['channel']}) was approved by "
            f"{event['approved_by']} with Brand Score {event['brand_score']}. "
            f"<{event['receipt_url']}|View the Review Receipt>"
        )
    return {"text": text, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}


# --- delivery -----------------------------------------------------------------------------


def _spawn(target: Callable[[], None], name: str) -> None:
    """Background work (tests replace this to run it inline)."""
    threading.Thread(target=target, daemon=True, name=name).start()


def _attempt(webhook: Webhook, event: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "at": utcnow().isoformat(),
        "status_code": status_code,
        "error": error,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "ok": status_code is not None and 200 <= status_code < 300,
    }


def _retryable(attempt: dict[str, Any]) -> bool:
    code = attempt["status_code"]
    return not attempt["ok"] and (code is None or code >= 500 or code in (408, 429))


def _record(delivery: WebhookDelivery, attempt: dict[str, Any]) -> None:
    delivery.attempt_log = [*delivery.attempt_log, attempt]
    delivery.attempts = len(delivery.attempt_log)
    delivery.status_code, delivery.error = attempt["status_code"], attempt["error"]
    delivery.latency_ms, delivery.ok = attempt["latency_ms"], attempt["ok"]
    final = attempt["ok"] or not _retryable(attempt) or delivery.attempts >= MAX_ATTEMPTS
    delivery.status = "delivered" if attempt["ok"] else "failed" if final else "retrying"


def _retry(session: Session, delivery: WebhookDelivery, webhook: Webhook) -> None:
    while delivery.status == "retrying":
        time.sleep(BACKOFF_SECONDS * 2 ** (delivery.attempts - 1))
        _record(delivery, _attempt(webhook, delivery.payload or {}))
        session.commit()


def _retry_in_background(delivery_id: int) -> None:
    def run() -> None:
        with session_factory() as session:
            delivery = session.get(WebhookDelivery, delivery_id)
            webhook = session.get(Webhook, delivery.webhook_id) if delivery else None
            if delivery is None or webhook is None:
                return
            try:
                _retry(session, delivery, webhook)
            except Exception:
                log.exception("webhook delivery %s retry failed", delivery_id)

    _spawn(run, f"webhook-retry-{delivery_id}")


def deliver(
    session: Session,
    webhook: Webhook,
    event: dict[str, Any],
    resent_from: int | None = None,
    wait: bool = True,
) -> WebhookDelivery:
    """Send now. Retries either happen here (`wait`, for background callers) or in a thread,
    so a request handler returns after the first attempt with status "retrying"."""
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event=event["event"],
        payload=event,
        resent_from=resent_from,
        attempt_log=[],
        latency_ms=0,
        ok=False,
    )
    _record(delivery, _attempt(webhook, event))
    session.add(delivery)
    session.commit()
    if delivery.status == "retrying":
        if wait:
            _retry(session, delivery, webhook)
        else:
            _retry_in_background(delivery.id)
    return delivery


def _dispatch(
    name: str,
    submission_id: str,
    build: Callable[[Session, Submission], dict[str, Any] | None],
) -> None:
    """Fire-and-forget: deliver one event to every active webhook subscribed to it."""

    def run() -> None:
        with session_factory() as session:
            submission = session.get(Submission, submission_id)
            if submission is None:
                return
            hooks = list(
                session.scalars(
                    select(Webhook).where(
                        Webhook.workspace_id == submission.workspace_id,
                        Webhook.active.is_(True),
                    )
                )
            )
            hooks = [w for w in hooks if name in w.events]
            event = build(session, submission) if hooks else None
            if event is None:
                return
            for webhook in hooks:
                try:
                    deliver(session, webhook, event)
                except Exception:
                    log.exception("webhook %s failed", webhook.id)

    _spawn(run, f"webhook-{name}-{submission_id}")


def dispatch_approval(submission_id: str) -> None:
    _dispatch("submission.approved", submission_id, approval_event)


def dispatch_published(submission_id: str, user_id: str) -> None:
    def build(session: Session, submission: Submission) -> dict[str, Any]:
        return published_event(session, submission, session.get_one(User, user_id))

    _dispatch("review.published", submission_id, build)


def dispatch_critical(submission_id: str, revision_id: str) -> None:
    def build(session: Session, _submission: Submission) -> dict[str, Any] | None:
        return critical_event(session, session.get_one(Revision, revision_id))

    _dispatch("finding.critical", submission_id, build)
