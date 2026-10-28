"""SQLAlchemy models. Entity names follow the Round 1 plan's data model."""

import enum
import secrets
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


def _enum(cls: type[enum.Enum]) -> Enum:
    return Enum(cls, native_enum=False, values_callable=lambda e: [m.value for m in e], length=32)


class Role(str, enum.Enum):
    creator = "creator"
    reviewer = "reviewer"
    brand_manager = "brand_manager"
    approver = "approver"
    admin = "admin"


class Severity(str, enum.Enum):
    critical = "critical"
    major = "major"
    minor = "minor"


class RuleStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    retired = "retired"


class SubmissionState(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    changes_requested = "changes_requested"
    approved = "approved"
    published = "published"


class TermKind(str, enum.Enum):
    product_name = "product_name"
    banned = "banned"
    discouraged = "discouraged"


TEMPLATE_WORKSPACE_ID = "ws_paywise"
TEMPLATE_KIND = "template"
SANDBOX_KIND = "sandbox"


class Workspace(Base):
    """A brand workspace. The seeded template is cloned into one sandbox per demo visitor."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default=TEMPLATE_KIND)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voice_profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rulebook_version: Mapped[int] = mapped_column(Integer, default=1)
    factbook_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    """A workspace member. Sandbox users are copies of the template's demo personas; `persona`
    keeps the template user's id so the role switcher can map between them."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    persona: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(_enum(Role))
    title: Mapped[str] = mapped_column(String(120), default="")


class Rule(Base):
    """A brand rule. Each edit creates a new row with version + 1; old versions are retired."""

    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("workspace_id", "code", "version"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    code: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(_enum(Severity))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source_doc: Mapped[str] = mapped_column(String(200))
    source_page: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[RuleStatus] = mapped_column(_enum(RuleStatus), default=RuleStatus.active)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def source_ref(self) -> str:
        return f"{self.source_doc}#p{self.source_page}" if self.source_page else self.source_doc


class Fact(Base):
    """An approved fact. Validity dates and `superseded_by` let the Claim Ledger spot outdated
    claims."""

    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(16), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    statement: Mapped[str] = mapped_column(Text)
    source_doc: Mapped[str] = mapped_column(String(200))
    source_page: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[RuleStatus] = mapped_column(_enum(RuleStatus), default=RuleStatus.active)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def source_ref(self) -> str:
        return f"{self.source_doc}#p{self.source_page}" if self.source_page else self.source_doc

    def is_current(self, on: date) -> bool:
        if self.status != RuleStatus.active or self.superseded_by:
            return False
        if self.valid_from and on < self.valid_from:
            return False
        return not (self.valid_until and on > self.valid_until)


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    term: Mapped[str] = mapped_column(String(120))
    kind: Mapped[TermKind] = mapped_column(_enum(TermKind))
    variants: Mapped[list[Any]] = mapped_column(default=list)
    replacement: Mapped[str | None] = mapped_column(String(120))
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_code: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")


class ChannelProfile(Base):
    __tablename__ = "channel_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(32))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(80))
    max_chars: Mapped[int | None] = mapped_column(Integer)
    max_hashtags: Mapped[int | None] = mapped_column(Integer)
    subject_max_chars: Mapped[int | None] = mapped_column(Integer)
    consumer: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_code: Mapped[str | None] = mapped_column(String(16))


class ConfidentialTerm(Base):
    __tablename__ = "confidential_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    term: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")


class SampleDraft(Base):
    __tablename__ = "sample_drafts"
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(32))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    label: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(32))
    format: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str | None] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("sub"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    state: Mapped[SubmissionState] = mapped_column(
        _enum(SubmissionState), default=SubmissionState.draft
    )
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="submission", order_by="Revision.number"
    )


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("submission_id", "number"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("rev"))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_uri: Mapped[str | None] = mapped_column(String(300))
    source_format: Mapped[str] = mapped_column(String(16), default="text")
    normalised_doc: Mapped[dict[str, Any]] = mapped_column(default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    brand_score: Mapped[int | None] = mapped_column(Integer)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    # Checker runs, score breakdown, tone profile and AI disclosure for this revision.
    report: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rulebook_version: Mapped[int | None] = mapped_column(Integer)
    factbook_version: Mapped[int | None] = mapped_column(Integer)
    # Fingerprint of the rulebook, facts and channel a review ran against (the cache key).
    context_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="revisions")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("fnd"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    span: Mapped[dict[str, Any]] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    rule_code: Mapped[str] = mapped_column(String(16))
    rule_source: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[list[Any]] = mapped_column(default=list)
    severity: Mapped[Severity] = mapped_column(_enum(Severity))
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    detector: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="open")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    related: Mapped[list[Any]] = mapped_column(default=list)
    # Box on the page image for visual findings: {page, x, y, w, h} as fractions.
    region: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Text that replaces the span in the next draft (accepted suggestion or author's edit).
    applied_text: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Claim(Base):
    """One row of the Claim Ledger: every detected claim, including supported ones."""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("clm"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    span: Mapped[dict[str, Any]] = mapped_column()
    claim_type: Mapped[str] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(16))
    fact_id: Mapped[str | None] = mapped_column(String(16))
    current_fact_id: Mapped[str | None] = mapped_column(String(16))
    quote: Mapped[str | None] = mapped_column(Text)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    confidence: Mapped[float] = mapped_column(Float)
    steps: Mapped[list[Any]] = mapped_column(default=list)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("dec"))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("revisions.id"))
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id"))
    kind: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("cmt"))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ntf"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.id"))
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only, hash-chained: hash = sha256(prev_hash + canonical_json(event))."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Each workspace has its own chain, so resetting a sandbox never breaks another one.
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(48))
    actor_id: Mapped[str | None] = mapped_column(String(32))
    payload_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class AiCall(Base):
    """Log of every external or local AI call, summarised in the AI disclosure panel."""

    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("revisions.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(80))
    latency_ms: Mapped[int] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    masked: Mapped[bool] = mapped_column(Boolean, default=False)
    masked_count: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("key"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("whk"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(64))
    slack_format: Mapped[bool] = mapped_column(Boolean, default=False)
    events: Mapped[list[Any]] = mapped_column(default=lambda: ["submission.approved"])
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhooks.id"), index=True)
    event: Mapped[str] = mapped_column(String(48))
    status_code: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("evl"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    n_items: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)
    confusion: Mapped[dict[str, Any]] = mapped_column(default=dict)
    failures: Mapped[list[Any]] = mapped_column(default=list)
    latency_ms_p50: Mapped[float] = mapped_column(Float)
    latency_ms_p95: Mapped[float] = mapped_column(Float)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)


class IdempotencyKey(Base):
    """A stored response for an `Idempotency-Key`, so a repeated request is not applied twice."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevisionAsset(Base):
    """A page image of a visual revision (reduced, WebP). Served by an unguessable id, like a
    shared certificate link, so <img> tags can load it without a token."""

    __tablename__ = "revision_assets"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: f"ast_{secrets.token_hex(12)}"
    )
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String(32), default="image/webp")
    # How much the page was reduced from the original (for WCAG "large text").
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
