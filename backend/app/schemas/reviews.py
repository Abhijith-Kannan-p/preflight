"""API schemas for reviews, findings, decisions and the workflow."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRef(ORM):
    id: str
    name: str
    role: str
    title: str


class FindingOut(ORM):
    id: str
    type: str
    span: dict[str, int]
    text: str
    rule: dict[str, str]
    evidence: list[dict[str, Any]]
    severity: str
    confidence: float
    explanation: str
    suggestion: dict[str, Any] | None
    detector: str
    status: str
    needs_review: bool
    related: list[str]
    applied_text: str | None
    region: dict[str, Any] | None = None


class ClaimOut(ORM):
    id: str
    text: str
    span: dict[str, int]
    claim_type: str
    verdict: str
    fact_id: str | None
    current_fact_id: str | None
    quote: str | None
    scores: dict[str, Any]
    confidence: float
    steps: list[str]


class DecisionOut(ORM):
    id: str
    kind: str
    reason: str
    payload: dict[str, Any]
    finding_id: str | None
    revision_id: str | None
    actor: UserRef
    created_at: datetime


class RevisionSummary(ORM):
    id: str
    number: int
    brand_score: int | None
    review_status: str
    created_at: datetime


class RevisionOut(RevisionSummary):
    content: str
    blocks: list[dict[str, Any]]
    source_format: str
    degraded: bool
    report: dict[str, Any]
    completed_at: datetime | None


class Gate(BaseModel):
    can_submit: bool
    can_approve: bool
    blocking: list[str]
    message: str


class SubmissionOut(ORM):
    id: str
    title: str
    channel: str
    state: str
    author: UserRef
    approved_by: UserRef | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class Clearance(BaseModel):
    approver: str
    at: datetime
    audit_hash: str
    overrides: int


class ReviewOut(BaseModel):
    submission: SubmissionOut
    revision: RevisionOut
    revisions: list[RevisionSummary]
    findings: list[FindingOut]
    claims: list[ClaimOut]
    decisions: list[DecisionOut]
    gate: Gate
    pending_edits: int
    permissions: list[str]
    clearance: Clearance | None = None
    # 1-based place in the review queue while the latest revision waits for a worker.
    queue_position: int | None = None


class ReviewListItem(BaseModel):
    id: str
    title: str
    channel: str
    state: str
    author: UserRef
    brand_score: int | None
    open_criticals: int
    open_findings: int
    revision: int
    review_status: str
    updated_at: datetime


class CreatedReview(BaseModel):
    id: str
    revision_id: str


class DecisionIn(BaseModel):
    kind: Literal["accept", "edit", "dispute", "escalate", "reopen"]
    reason: str = Field(default="", max_length=2000)
    text: str | None = Field(default=None, max_length=2000)


class RecheckIn(BaseModel):
    content: str | None = Field(default=None, max_length=20_000)
    use_draft: bool = True


class Override(BaseModel):
    finding_id: str
    reason: str = Field(min_length=10, max_length=2000)


class TransitionIn(BaseModel):
    action: Literal["submit", "request_changes", "approve", "publish"]
    comment: str = Field(default="", max_length=4000)
    overrides: list[Override] = Field(default_factory=list)


class DraftOut(BaseModel):
    content: str
    applied: int
    changed: bool


class DiffOut(BaseModel):
    from_number: int
    to_number: int
    from_text: str
    to_text: str
    from_score: int | None
    to_score: int | None
    resolved: list[FindingOut]
    introduced: list[FindingOut]


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    finding_id: str | None = None


class CommentOut(ORM):
    id: str
    body: str
    finding_id: str | None
    author: UserRef
    created_at: datetime


class NotificationOut(ORM):
    id: str
    kind: str
    message: str
    submission_id: str | None
    read: bool
    created_at: datetime
