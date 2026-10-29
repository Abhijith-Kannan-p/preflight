"""Per-visitor demo sandboxes.

Each visitor gets a private workspace cloned from the seeded PayWise template: brand rules,
facts (with their embeddings), terms, channels, samples, the five demo personas and the
generated review history. The clone runs as `INSERT ... SELECT` inside the database, with
every copied id suffixed so foreign keys stay consistent, so it takes well under a second.
The audit chain is re-hashed for the new workspace so it verifies on its own.

Sandboxes expire after 24 hours without activity; a background sweep deletes them.
"""

import logging
import secrets
import threading
import time
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import Column, CursorResult, Table, delete, select, text
from sqlalchemy.orm import Session

from app import audit
from app.idempotency import purge_expired
from app.models import (
    SANDBOX_KIND,
    TEMPLATE_WORKSPACE_ID,
    AiCall,
    ApiKey,
    AuditEvent,
    Base,
    ChannelProfile,
    Claim,
    Comment,
    CompileJob,
    ConfidentialTerm,
    Decision,
    Fact,
    Finding,
    IdempotencyKey,
    Notification,
    Revision,
    RevisionAsset,
    Rule,
    RuleCandidate,
    SampleDraft,
    Submission,
    Term,
    User,
    Webhook,
    WebhookDelivery,
    Workspace,
    utcnow,
)

log = logging.getLogger(__name__)

IDLE_LIMIT = timedelta(hours=24)
MAX_SANDBOXES = 500
SWEEP_EVERY_SECONDS = 30 * 60

# Brand tables are copied by workspace; history tables by their parent (see `_rows_of`).
# String ids of copied history rows and users get the sandbox suffix.
_BRAND: tuple[type[Base], ...] = (Rule, Fact, Term, ChannelProfile, ConfidentialTerm, SampleDraft)
_HISTORY: tuple[type[Base], ...] = (
    Submission,
    Revision,
    Finding,
    Claim,
    AiCall,
    Decision,
    Comment,
    Notification,
)
_HISTORY_IDS = {
    "submissions",
    "revisions",
    "findings",
    "claims",
    "decisions",
    "comments",
    "notifications",
}


def _rows_of(table: str) -> str:
    """WHERE clause selecting the template's rows of a history table."""
    subs = "SELECT id FROM submissions WHERE workspace_id = :t"
    revs = f"SELECT id FROM revisions WHERE submission_id IN ({subs})"
    return {
        "submissions": "workspace_id = :t",
        "revisions": f"submission_id IN ({subs})",
        "findings": f"revision_id IN ({revs})",
        "claims": f"revision_id IN ({revs})",
        "ai_calls": f"revision_id IN ({revs})",
        "decisions": f"submission_id IN ({subs})",
        "comments": f"submission_id IN ({subs})",
        "notifications": "user_id IN (SELECT id FROM users WHERE workspace_id = :t)",
    }[table]


def _expression(column: Column[Any]) -> str | None:
    """How one column is written into the clone (None: let the database assign it)."""
    name = column.name
    if column.primary_key and column.autoincrement is True and str(column.type) == "INTEGER":
        return None
    if name == "workspace_id":
        return ":ws"
    targets = {fk.column.table.name for fk in column.foreign_keys}
    suffix = None
    if "users" in targets or (column.primary_key and column.table.name == "users"):
        suffix = ":us"
    elif targets & _HISTORY_IDS or (column.primary_key and column.table.name in _HISTORY_IDS):
        suffix = ":hs"
    if suffix is None:
        return name
    return f"CASE WHEN {name} IS NULL THEN NULL ELSE {name} || {suffix} END"


def _copy(session: Session, model: type[Base], where: str, params: dict[str, str]) -> int:
    table = cast(Table, model.__table__)
    pairs = [(c.name, _expression(c)) for c in table.columns]
    pairs = [(n, e) for n, e in pairs if e is not None]
    columns = ", ".join(n for n, _ in pairs)
    values = ", ".join(e for _, e in pairs if e)
    sql = f"INSERT INTO {table.name} ({columns}) SELECT {values} FROM {table.name} WHERE {where}"
    result = cast(CursorResult[Any], session.execute(text(sql), params))
    return result.rowcount


def _copy_audit(session: Session, template: str, ws: str, us: str, hs: str, ids: set[str]) -> int:
    """Re-chain the template's audit events for the clone, remapping ids that were copied."""

    def remap(value: Any) -> Any:
        if isinstance(value, str):
            if value in ids:
                return value + hs
            if value.startswith("usr_"):
                return value + us
            if value == template:
                return ws
        return value

    events = session.scalars(
        select(AuditEvent).where(AuditEvent.workspace_id == template).order_by(AuditEvent.id)
    ).all()
    prev = audit.GENESIS
    for e in events:
        copy = AuditEvent(
            workspace_id=ws,
            entity=e.entity,
            entity_id=remap(e.entity_id),
            action=e.action,
            actor_id=remap(e.actor_id),
            payload_json={k: remap(v) for k, v in e.payload_json.items()},
            ts=e.ts,
            prev_hash=prev,
        )
        copy.hash = audit.compute_hash(prev, copy)
        prev = copy.hash
        session.add(copy)
    return len(events)


def _clone_into(session: Session, template: str, ws: str) -> dict[str, int]:
    """Copy the template's brand, personas, history and audit chain into workspace `ws`."""
    token = secrets.token_hex(4)
    params = {"t": template, "ws": ws, "us": f"_{token}", "hs": f"_{token}"}
    counts = {"users": _copy(session, User, "workspace_id = :t", params)}
    for brand in _BRAND:
        counts[brand.__tablename__] = _copy(session, brand, "workspace_id = :t", params)
    history_ids: set[str] = set()
    for model in _HISTORY:
        name = model.__tablename__
        if name in _HISTORY_IDS:
            history_ids |= set(
                session.scalars(text(f"SELECT id FROM {name} WHERE {_rows_of(name)}"), params)
            )
        counts[name] = _copy(session, model, _rows_of(name), params)
    counts["audit_events"] = _copy_audit(
        session, template, ws, params["us"], params["hs"], history_ids
    )
    return counts


# One clone at a time: each holds the template's audit chain in memory while re-chaining it,
# and five visitors arriving together would otherwise hold five copies on a 512 MB host.
_clone_lock = threading.Lock()


def create_sandbox(session: Session, template: str = TEMPLATE_WORKSPACE_ID) -> Workspace:
    """Clone the template into a new sandbox workspace and commit it."""
    started = time.perf_counter()
    ws = f"sbx_{secrets.token_hex(6)}"
    source = session.get_one(Workspace, template)
    now = utcnow()
    session.add(
        Workspace(
            id=ws,
            name=source.name,
            kind=SANDBOX_KIND,
            voice_profile=source.voice_profile,
            settings=source.settings,
            rulebook_version=source.rulebook_version,
            factbook_version=source.factbook_version,
            created_at=now,
            last_active_at=now,
        )
    )
    session.flush()
    with _clone_lock:
        counts = _clone_into(session, template, ws)
        session.commit()
    log.info(
        "sandbox %s created in %.0f ms: %s", ws, (time.perf_counter() - started) * 1000, counts
    )
    return session.get_one(Workspace, ws)


def reset_sandbox(session: Session, workspace_id: str) -> Workspace:
    """Put a sandbox back to the template's state, keeping its id (and the visitor's cookie).
    Personas get fresh ids, so callers must issue a new token."""
    workspace = session.get_one(Workspace, workspace_id)
    if workspace.kind != SANDBOX_KIND:
        raise ValueError("only sandboxes can be reset this way")
    clear_workspace(session, workspace_id)
    source = session.get_one(Workspace, TEMPLATE_WORKSPACE_ID)
    workspace.voice_profile, workspace.settings = source.voice_profile, source.settings
    # Versions move forward so nothing cached against the old rulebook is reused by mistake.
    workspace.rulebook_version = max(workspace.rulebook_version, source.rulebook_version) + 1
    workspace.factbook_version = max(workspace.factbook_version, source.factbook_version) + 1
    workspace.last_active_at = utcnow()
    session.flush()
    with _clone_lock:
        _clone_into(session, TEMPLATE_WORKSPACE_ID, workspace_id)
        session.commit()
    return workspace


def clear_workspace(session: Session, workspace_id: str) -> None:
    """Delete everything inside a workspace (reviews, brand, members, keys, audit chain),
    keeping the workspace row itself. Does not commit."""
    subs = select(Submission.id).where(Submission.workspace_id == workspace_id)
    revs = select(Revision.id).where(Revision.submission_id.in_(subs))
    users = select(User.id).where(User.workspace_id == workspace_id)
    hooks = select(Webhook.id).where(Webhook.workspace_id == workspace_id)
    session.execute(delete(WebhookDelivery).where(WebhookDelivery.webhook_id.in_(hooks)))
    session.execute(delete(Webhook).where(Webhook.workspace_id == workspace_id))
    jobs = select(CompileJob.id).where(CompileJob.workspace_id == workspace_id)
    session.execute(delete(RuleCandidate).where(RuleCandidate.job_id.in_(jobs)))
    session.execute(delete(CompileJob).where(CompileJob.workspace_id == workspace_id))
    session.execute(delete(ApiKey).where(ApiKey.workspace_id == workspace_id))
    session.execute(delete(Notification).where(Notification.user_id.in_(users)))
    session.execute(delete(IdempotencyKey).where(IdempotencyKey.scope.in_(users)))
    session.execute(delete(Comment).where(Comment.submission_id.in_(subs)))
    session.execute(delete(Decision).where(Decision.submission_id.in_(subs)))
    session.execute(delete(RevisionAsset).where(RevisionAsset.revision_id.in_(revs)))
    session.execute(delete(AiCall).where(AiCall.revision_id.in_(revs)))
    session.execute(delete(Claim).where(Claim.revision_id.in_(revs)))
    session.execute(delete(Finding).where(Finding.revision_id.in_(revs)))
    session.execute(delete(Revision).where(Revision.submission_id.in_(subs)))
    session.execute(delete(Submission).where(Submission.workspace_id == workspace_id))
    session.execute(delete(AuditEvent).where(AuditEvent.workspace_id == workspace_id))
    for model in _BRAND:
        session.execute(delete(model).where(model.__table__.c.workspace_id == workspace_id))
    session.execute(delete(User).where(User.workspace_id == workspace_id))
    session.expire_all()


def delete_workspace(session: Session, workspace_id: str) -> None:
    """Delete a sandbox and everything in it. The template can never be deleted."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.kind != SANDBOX_KIND:
        return
    clear_workspace(session, workspace_id)
    session.execute(delete(Workspace).where(Workspace.id == workspace_id))
    session.commit()


def find_user(session: Session, workspace_id: str, user_id: str | None) -> User | None:
    """A workspace member by id, or by the template persona id (`usr_abhi1`)."""
    wanted = user_id or "usr_abhi1"
    return session.scalar(
        select(User).where(
            User.workspace_id == workspace_id, (User.id == wanted) | (User.persona == wanted)
        )
    )


def live_sandbox(session: Session, workspace_id: str | None) -> Workspace | None:
    if not workspace_id:
        return None
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.kind != SANDBOX_KIND:
        return None
    last = workspace.last_active_at or workspace.created_at
    if utcnow() - last > IDLE_LIMIT:
        delete_workspace(session, workspace_id)
        return None
    return workspace


def sweep(session: Session) -> int:
    """Delete idle sandboxes, and the oldest ones beyond the cap. Returns how many."""
    cutoff = utcnow() - IDLE_LIMIT
    sandboxes = session.scalars(
        select(Workspace)
        .where(Workspace.kind == SANDBOX_KIND)
        .order_by(Workspace.last_active_at.desc().nulls_last())
    ).all()
    doomed = [
        w.id
        for i, w in enumerate(sandboxes)
        if i >= MAX_SANDBOXES or (w.last_active_at or w.created_at) < cutoff
    ]
    for workspace_id in doomed:
        delete_workspace(session, workspace_id)
    if doomed:
        log.info("swept %d idle sandboxes", len(doomed))
    return len(doomed)


def start_sweeper() -> None:
    from app.db import SessionLocal

    def loop() -> None:
        while True:
            try:
                with SessionLocal() as session:
                    sweep(session)
                    purge_expired(session)
            except Exception:
                log.exception("sandbox sweep failed")
            time.sleep(SWEEP_EVERY_SECONDS)

    threading.Thread(target=loop, daemon=True, name="sandbox-sweeper").start()
