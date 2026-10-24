"""API response schemas for the Brand Knowledge Base (rulebook)."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


# --- inputs for editing the Brand Knowledge Base ----------------------------------------


class RuleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{3}-\d{2}$", description="e.g. CLM-09")
    category: Literal["claims", "terminology", "tone", "disclaimer", "channel", "readability"]
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    severity: Literal["critical", "major", "minor"]
    config: dict[str, Any] = Field(default_factory=dict)
    source_doc: str = Field(min_length=1, max_length=200)
    source_page: int | None = Field(default=None, ge=1)


class RuleUpdate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    severity: Literal["critical", "major", "minor"]
    config: dict[str, Any] = Field(default_factory=dict)
    source_doc: str = Field(min_length=1, max_length=200)
    source_page: int | None = Field(default=None, ge=1)


class FactIn(BaseModel):
    id: str = Field(pattern=r"^F-\d{3,4}$", description="e.g. F-401")
    statement: str = Field(min_length=5, max_length=1000)
    source_doc: str = Field(min_length=1, max_length=200)
    source_page: int | None = Field(default=None, ge=1)
    valid_from: date | None = None
    valid_until: date | None = None


class FactUpdate(BaseModel):
    statement: str = Field(min_length=5, max_length=1000)
    source_doc: str = Field(min_length=1, max_length=200)
    source_page: int | None = Field(default=None, ge=1)
    valid_from: date | None = None
    valid_until: date | None = None


class SupersedeIn(BaseModel):
    new_id: str = Field(pattern=r"^F-\d{3,4}$")
    statement: str = Field(min_length=5, max_length=1000)
    source_doc: str = Field(min_length=1, max_length=200)
    source_page: int | None = Field(default=None, ge=1)
    valid_from: date


class TermIn(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    kind: Literal["product_name", "banned", "discouraged"]
    variants: list[str] = Field(default_factory=list, max_length=30)
    replacement: str | None = Field(default=None, max_length=120)
    case_sensitive: bool = False
    rule_code: str = Field(pattern=r"^[A-Z]{3}-\d{2}$")
    note: str = Field(default="", max_length=500)


class ChannelUpdate(BaseModel):
    max_chars: int | None = Field(default=None, ge=1)
    max_hashtags: int | None = Field(default=None, ge=0)
    subject_max_chars: int | None = Field(default=None, ge=1)
    consumer: bool = True


class ConfidentialIn(BaseModel):
    term: str = Field(min_length=2, max_length=200)
    kind: str = Field(default="project", max_length=32)
    note: str = Field(default="", max_length=500)


class ImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    errors: list[str]
