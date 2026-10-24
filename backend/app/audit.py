"""Append-only, hash-chained audit log.

hash = sha256(prev_hash + canonical_json(event)). Appends are serialised with a Postgres
advisory lock so two concurrent requests can never fork the chain. `verify_chain` recomputes
every hash and reports the first broken link.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditEvent, utcnow

GENESIS = "0" * 64
_LOCK_KEY = 4_242_001


def canonical_json(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _event_body(e: AuditEvent) -> dict[str, Any]:
    ts: datetime = e.ts
    return {
        "entity": e.entity,
        "entity_id": e.entity_id,
        "action": e.action,
        "actor_id": e.actor_id,
        "payload": e.payload_json,
        "ts": ts.isoformat(),
    }


def compute_hash(prev_hash: str, event: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + canonical_json(_event_body(event))).encode()).hexdigest()


def record(
    session: Session,
    entity: str,
    entity_id: str,
    action: str,
    actor_id: str | None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an event in the caller's transaction (committed with the change it describes)."""
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    last = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)).first()
    event = AuditEvent(
        entity=entity,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        payload_json=json.loads(canonical_json(payload or {})),
        ts=utcnow(),
        prev_hash=last.hash if last else GENESIS,
    )
    event.hash = compute_hash(event.prev_hash, event)
    session.add(event)
    session.flush()
    return event


class ChainStatus(BaseModel):
    intact: bool
    events: int
    broken_at: int | None = None
    message: str


def verify_chain(session: Session) -> ChainStatus:
    prev = GENESIS
    count = 0
    for event in session.scalars(select(AuditEvent).order_by(AuditEvent.id)):
        count += 1
        if event.prev_hash != prev or compute_hash(prev, event) != event.hash:
            return ChainStatus(
                intact=False,
                events=count,
                broken_at=event.id,
                message=f"Chain broken at event #{event.id} ({event.action} on {event.entity_id}).",
            )
        prev = event.hash
    return ChainStatus(intact=True, events=count, message=f"Chain intact: {count} events verified.")
