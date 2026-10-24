"""Everything a review needs from the Brand Knowledge Base, as plain immutable data.

Checkers depend on this snapshot, not on the database, so they are pure and easy to test.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChannelProfile,
    ConfidentialTerm,
    Fact,
    Rule,
    RuleStatus,
    Term,
    Workspace,
)


@dataclass(frozen=True)
class RuleInfo:
    code: str
    category: str
    title: str
    severity: str
    config: dict[str, Any]
    source_ref: str


@dataclass(frozen=True)
class TermInfo:
    term: str
    kind: str
    variants: tuple[str, ...]
    replacement: str | None
    case_sensitive: bool
    rule_code: str


@dataclass(frozen=True)
class ChannelInfo:
    id: str
    name: str
    max_chars: int | None
    max_hashtags: int | None
    subject_max_chars: int | None
    consumer: bool
    rule_code: str | None


@dataclass(frozen=True)
class FactInfo:
    id: str
    statement: str
    source_ref: str
    valid_from: date | None
    valid_until: date | None
    superseded_by: str | None
    current: bool
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class ReviewContext:
    rules: dict[str, RuleInfo]
    terms: tuple[TermInfo, ...]
    channel: ChannelInfo | None
    facts: dict[str, FactInfo]
    voice: dict[str, Any]
    confidential: tuple[str, ...]
    today: date
    rulebook_version: int = 1
    factbook_version: int = 1
    settings: dict[str, Any] = field(default_factory=dict)

    def rule(self, code: str) -> RuleInfo | None:
        return self.rules.get(code)


def load_context(
    session: Session, workspace_id: str, channel_id: str, today: date | None = None
) -> ReviewContext:
    on = today or date.today()
    workspace = session.get_one(Workspace, workspace_id)
    rules: dict[str, RuleInfo] = {}
    for r in session.scalars(
        select(Rule)
        .where(Rule.workspace_id == workspace_id, Rule.status == RuleStatus.active)
        .order_by(Rule.code, Rule.version)
    ):
        rules[r.code] = RuleInfo(
            r.code, r.category, r.title, r.severity.value, r.config, r.source_ref
        )
    terms = tuple(
        TermInfo(
            t.term, t.kind.value, tuple(t.variants), t.replacement, t.case_sensitive, t.rule_code
        )
        for t in session.scalars(select(Term).where(Term.workspace_id == workspace_id))
    )
    channel_row = session.get(ChannelProfile, channel_id)
    channel = (
        ChannelInfo(
            channel_row.id,
            channel_row.name,
            channel_row.max_chars,
            channel_row.max_hashtags,
            channel_row.subject_max_chars,
            channel_row.consumer,
            channel_row.rule_code,
        )
        if channel_row
        else None
    )
    facts = {
        f.id: FactInfo(
            f.id,
            f.statement,
            f.source_ref,
            f.valid_from,
            f.valid_until,
            f.superseded_by,
            f.is_current(on),
            tuple(float(x) for x in f.embedding) if f.embedding is not None else None,
        )
        for f in session.scalars(
            select(Fact).where(Fact.workspace_id == workspace_id, Fact.status == RuleStatus.active)
        )
    }
    confidential = tuple(
        session.scalars(
            select(ConfidentialTerm.term).where(ConfidentialTerm.workspace_id == workspace_id)
        )
    )
    return ReviewContext(
        rules=rules,
        terms=terms,
        channel=channel,
        facts=facts,
        voice=workspace.voice_profile,
        confidential=confidential,
        today=on,
        rulebook_version=workspace.rulebook_version,
        factbook_version=workspace.factbook_version,
        settings=workspace.settings,
    )
