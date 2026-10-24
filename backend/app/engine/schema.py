"""The typed Finding contract and the normalised document every checker works on."""

import secrets
from typing import Literal

from pydantic import BaseModel, Field

FindingType = Literal[
    "unsupported_claim",
    "outdated_fact",
    "contradicted_claim",
    "terminology",
    "banned_phrase",
    "tone",
    "disclaimer",
    "channel",
    "readability",
]
SeverityLevel = Literal["critical", "major", "minor"]
Detector = Literal["rules", "llm", "nli"]
FindingStatus = Literal["open", "accepted", "edited", "disputed", "escalated", "resolved"]
NliLabel = Literal["entailment", "neutral", "contradiction"]

SEVERITY_WEIGHT: dict[str, int] = {"critical": 3, "major": 2, "minor": 1}


class Block(BaseModel):
    id: int
    text: str
    start_offset: int


class NormalisedDoc(BaseModel):
    blocks: list[Block]
    source_format: str = "text"

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    @property
    def word_count(self) -> int:
        return sum(len(b.text.split()) for b in self.blocks)


class Span(BaseModel):
    block: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class RuleRef(BaseModel):
    id: str
    source: str


class Evidence(BaseModel):
    fact_id: str
    quote: str
    nli: NliLabel | None = None
    score: float | None = None


class Suggestion(BaseModel):
    text: str
    drift: float | None = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: f"fnd_{secrets.token_hex(4)}")
    type: FindingType
    span: Span
    text: str
    rule: RuleRef
    evidence: list[Evidence] = Field(default_factory=list)
    severity: SeverityLevel
    confidence: float = Field(ge=0, le=1)
    explanation: str
    suggestion: Suggestion | None = None
    detector: Detector
    status: FindingStatus = "open"
    needs_review: bool = False
    related: list[str] = Field(default_factory=list)

    @property
    def rank(self) -> float:
        return SEVERITY_WEIGHT[self.severity] * self.confidence
