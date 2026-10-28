"""Load the fictional PayWise demo brand into the database.

Idempotent: running it again updates rows in place instead of duplicating them.
Usage: python -m app.seed [--if-empty]
"""

import argparse
import csv
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ml.embeddings import Embedder, get_embedder
from app.models import (
    TEMPLATE_WORKSPACE_ID,
    ChannelProfile,
    ConfidentialTerm,
    Fact,
    Role,
    Rule,
    RuleStatus,
    SampleDraft,
    Severity,
    Term,
    TermKind,
    User,
    Workspace,
)
from app.scoped import get_channel, get_fact, get_sample

log = logging.getLogger(__name__)

WORKSPACE_ID = TEMPLATE_WORKSPACE_ID


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def seed_workspace(session: Session, data_dir: Path) -> Workspace:
    raw = _read_json(data_dir / "workspace.json")
    ws = session.get(Workspace, raw["id"]) or Workspace(id=raw["id"])
    ws.name = raw["name"]
    ws.voice_profile = raw["voice_profile"]
    ws.settings = {**raw["settings"], **(ws.settings or {})}
    session.add(ws)
    session.flush()
    for u in raw["users"]:
        user = session.get(User, u["id"]) or User(id=u["id"])
        user.workspace_id, user.persona = ws.id, u["id"]
        user.name, user.email, user.title = u["name"], u["email"], u["title"]
        user.role = Role(u["role"])
        session.add(user)
    session.flush()
    return ws


def seed_rules(session: Session, data_dir: Path, workspace_id: str) -> int:
    rows = _read_csv(data_dir / "rules.csv")
    for row in rows:
        version = int(row["version"])
        rule = session.scalar(
            select(Rule).where(
                Rule.workspace_id == workspace_id, Rule.code == row["id"], Rule.version == version
            )
        ) or Rule(workspace_id=workspace_id, code=row["id"], version=version)
        rule.category = row["category"]
        rule.title = row["title"]
        rule.description = row["description"]
        rule.severity = Severity(row["severity"])
        rule.config = json.loads(row["config"])
        rule.source_doc = row["source_doc"]
        rule.source_page = int(row["source_page"]) if row["source_page"] else None
        rule.status = RuleStatus(row["status"])
        rule.created_by = row["created_by"] or None
        rule.approved_by = row["approved_by"] or None
        session.add(rule)
    return len(rows)


def seed_facts(
    session: Session, data_dir: Path, workspace_id: str, embedder: Embedder | None
) -> int:
    rows = _read_csv(data_dir / "facts.csv")
    to_embed: list[Fact] = []
    for row in rows:
        fact = get_fact(session, workspace_id, row["id"]) or Fact(
            id=row["id"], workspace_id=workspace_id
        )
        if fact.statement != row["statement"]:
            fact.embedding = None
        fact.statement = row["statement"]
        fact.source_doc = row["source_doc"]
        fact.source_page = int(row["source_page"]) if row["source_page"] else None
        fact.valid_from = _date(row["valid_from"])
        fact.valid_until = _date(row["valid_until"])
        fact.superseded_by = row["superseded_by"] or None
        fact.status = RuleStatus.active
        fact.created_by, fact.approved_by = "usr_abhi3", "usr_abhi4"
        session.add(fact)
        if fact.embedding is None:
            to_embed.append(fact)
    if embedder and to_embed:
        vectors = embedder.embed([f.statement for f in to_embed])
        for fact, vector in zip(to_embed, vectors, strict=True):
            fact.embedding = vector
    return len(rows)


def seed_terms(session: Session, data_dir: Path, workspace_id: str) -> int:
    rows = _read_csv(data_dir / "terms.csv")
    for row in rows:
        kind = TermKind(row["kind"])
        term = session.scalar(
            select(Term).where(
                Term.workspace_id == workspace_id, Term.term == row["term"], Term.kind == kind
            )
        ) or Term(workspace_id=workspace_id, term=row["term"], kind=kind)
        term.variants = [v for v in row["variants"].split("|") if v]
        term.replacement = row["replacement"] or None
        term.case_sensitive = row["case_sensitive"].lower() == "true"
        term.rule_code = row["rule_id"]
        term.note = row["note"]
        session.add(term)
    return len(rows)


def seed_channels(session: Session, data_dir: Path, workspace_id: str) -> int:
    rows = _read_json(data_dir / "channels.json")
    for row in rows:
        channel = get_channel(session, workspace_id, row["id"]) or ChannelProfile(id=row["id"])
        channel.workspace_id = workspace_id
        for key in ("name", "max_chars", "max_hashtags", "subject_max_chars", "consumer"):
            setattr(channel, key, row[key])
        channel.rule_code = row["rule_code"]
        session.add(channel)
    return len(rows)


def seed_confidential(session: Session, data_dir: Path, workspace_id: str) -> int:
    rows = _read_csv(data_dir / "confidential.csv")
    for row in rows:
        term = session.scalar(
            select(ConfidentialTerm).where(
                ConfidentialTerm.workspace_id == workspace_id,
                ConfidentialTerm.term == row["term"],
            )
        ) or ConfidentialTerm(workspace_id=workspace_id, term=row["term"])
        term.kind, term.note = row["kind"], row["note"]
        session.add(term)
    return len(rows)


def seed_samples(session: Session, data_dir: Path, workspace_id: str) -> int:
    rows = _read_json(data_dir / "drafts.json")
    for position, row in enumerate(rows):
        draft = get_sample(session, workspace_id, row["id"]) or SampleDraft(id=row["id"])
        draft.workspace_id = workspace_id
        for key in ("label", "title", "channel", "format", "filename", "content", "description"):
            setattr(draft, key, row[key])
        draft.position = position
        session.add(draft)
    return len(rows)


def _identity(embedder: Embedder) -> str:
    return str(getattr(embedder, "identity", embedder.name))


def ensure_fact_embeddings(session: Session, workspace_id: str, embedder: Embedder | None) -> int:
    """Re-embed every fact if the stored vectors came from a different embedding model, so
    queries and facts always share one vector space. Returns how many facts were embedded."""
    if embedder is None:
        return 0
    workspace = session.get_one(Workspace, workspace_id)
    identity = _identity(embedder)
    if workspace.settings.get("embedding_identity") == identity:
        return 0
    facts = list(session.scalars(select(Fact).where(Fact.workspace_id == workspace_id)))
    if facts:
        vectors = embedder.embed([f.statement for f in facts])
        for fact, vector in zip(facts, vectors, strict=True):
            fact.embedding = vector
    workspace.settings = {**workspace.settings, "embedding_identity": identity}
    session.commit()
    log.info("re-embedded %d facts with %s", len(facts), identity)
    return len(facts)


def seed_all(session: Session, data_dir: Path, embedder: Embedder | None) -> dict[str, int]:
    ws = seed_workspace(session, data_dir)
    counts = {
        "rules": seed_rules(session, data_dir, ws.id),
        "facts": seed_facts(session, data_dir, ws.id, embedder),
        "terms": seed_terms(session, data_dir, ws.id),
        "channels": seed_channels(session, data_dir, ws.id),
        "confidential_terms": seed_confidential(session, data_dir, ws.id),
        "sample_drafts": seed_samples(session, data_dir, ws.id),
    }
    session.commit()
    ensure_fact_embeddings(session, ws.id, embedder)
    return counts


def upgrade_template(session: Session, data_dir: Path) -> dict[str, int]:
    """Bring an existing template up to date with new seed data (new rules, samples, palette)
    without touching rows that are already there. Runs on every boot; a no-op when current."""
    ws = session.get_one(Workspace, WORKSPACE_ID)
    have = set(session.scalars(select(Rule.code).where(Rule.workspace_id == WORKSPACE_ID)))
    added_rules = 0
    for row in _read_csv(data_dir / "rules.csv"):
        if row["id"] in have:
            continue
        session.add(
            Rule(
                workspace_id=WORKSPACE_ID,
                code=row["id"],
                version=int(row["version"]),
                category=row["category"],
                title=row["title"],
                description=row["description"],
                severity=Severity(row["severity"]),
                config=json.loads(row["config"]),
                source_doc=row["source_doc"],
                source_page=int(row["source_page"]) if row["source_page"] else None,
                status=RuleStatus(row["status"]),
                created_by=row["created_by"] or None,
                approved_by=row["approved_by"] or None,
            )
        )
        added_rules += 1
    samples = set(
        session.scalars(select(SampleDraft.id).where(SampleDraft.workspace_id == WORKSPACE_ID))
    )
    wanted = {row["id"] for row in _read_json(data_dir / "drafts.json")}
    added_samples = len(wanted - samples)
    if added_samples:
        seed_samples(session, data_dir, WORKSPACE_ID)
    defaults = _read_json(data_dir / "workspace.json")["settings"]
    missing = {k: v for k, v in defaults.items() if k not in ws.settings}
    if missing:
        ws.settings = {**ws.settings, **missing}
    if added_rules:
        ws.rulebook_version += 1
    session.commit()
    return {"rules": added_rules, "samples": added_samples, "settings": len(missing)}


def is_empty(session: Session) -> bool:
    return session.get(Workspace, WORKSPACE_ID) is None


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Seed the PayWise demo brand.")
    parser.add_argument("--if-empty", action="store_true", help="only seed an empty database")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    data_dir = get_settings().seed_dir
    with SessionLocal() as session:
        if args.if_empty and not is_empty(session):
            # Still align fact vectors with the configured embedding model after an upgrade.
            upgraded = upgrade_template(session, data_dir)
            reembedded = ensure_fact_embeddings(session, WORKSPACE_ID, get_embedder())
            log.info(
                "database already seeded; added %s; re-embedded %d facts", upgraded, reembedded
            )
            return
        counts = seed_all(session, data_dir, get_embedder())
    log.info("seeded PayWise: %s", counts)


if __name__ == "__main__":
    main()
