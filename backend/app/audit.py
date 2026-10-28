"""Append-only, hash-chained audit log.

hash = sha256(prev_hash + canonical_json(event)). Each workspace has its own chain, so a demo
sandbox can be reset or expire without touching anyone else's. Appends are serialised per
workspace with a Postgres advisory lock so two concurrent requests can never fork a chain.
`verify_chain` recomputes every hash and reports the first broken link.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditEvent, User, utcnow

GENESIS = "0" * 64
_LOCK_NAMESPACE = 4242


def _lock_key(workspace_id: str) -> int:
    """A stable 31-bit advisory-lock key per workspace."""
    return int.from_bytes(hashlib.sha256(workspace_id.encode()).digest()[:4], "big") >> 1


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
    workspace_id: str | None = None,
) -> AuditEvent:
    """Append an event in the caller's transaction (committed with the change it describes).

    The workspace defaults to the actor's; system events must pass it explicitly."""
    if workspace_id is None:
        actor = session.get(User, actor_id) if actor_id else None
        if actor is None:
            raise ValueError("audit.record needs a workspace_id for events without an actor")
        workspace_id = actor.workspace_id
    session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :k)"),
        {"ns": _LOCK_NAMESPACE, "k": _lock_key(workspace_id)},
    )
    last = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.id.desc())
        .limit(1)
    ).first()
    event = AuditEvent(
        workspace_id=workspace_id,
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


def verify_chain(session: Session, workspace_id: str) -> ChainStatus:
    prev = GENESIS
    count = 0
    events = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
    for event in session.scalars(events.order_by(AuditEvent.id)):
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
