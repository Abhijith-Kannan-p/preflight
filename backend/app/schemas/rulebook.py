"""API response schemas for the Brand Knowledge Base (rulebook)."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    name: str
    email: str
    role: str
    title: str


class RuleOut(ORMModel):
    code: str
    category: str
    title: str
    description: str
    severity: str
    config: dict[str, Any]
    source_doc: str
    source_page: int | None
    source_ref: str
    version: int
    status: str
    created_by: str | None
    approved_by: str | None


class FactOut(ORMModel):
    id: str
    statement: str
    source_doc: str
    source_page: int | None
    source_ref: str
    valid_from: date | None
    valid_until: date | None
    superseded_by: str | None
    version: int
    status: str
    is_current: bool


class TermOut(ORMModel):
    id: int
    term: str
    kind: str
    variants: list[str]
    replacement: str | None
    case_sensitive: bool
    rule_code: str
    note: str


class ChannelOut(ORMModel):
    id: str
    name: str
    max_chars: int | None
    max_hashtags: int | None
    subject_max_chars: int | None
    consumer: bool
    rule_code: str | None


class ConfidentialTermOut(ORMModel):
    id: int
    term: str
    kind: str
    note: str


class SampleDraftOut(ORMModel):
    id: str
    label: str
    title: str
    channel: str
    format: str
    filename: str | None
    content: str
    description: str


class VoiceProfileOut(BaseModel):
    description: str
    traits: dict[str, float]
