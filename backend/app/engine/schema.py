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
    "visual",
    "accessibility",
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


class LineBox(BaseModel):
    """Where a stretch of a block's text sits on a page image (fractions of the page size)."""

    block: int
    start: int
    end: int
    page: int
    x: float
    y: float
    w: float
    h: float


class ImageRef(BaseModel):
    """An image in or of the document, with its alternative text (None: none given)."""

    name: str
    alt: str | None
    source: Literal["upload", "html", "docx"]


VISUAL_FORMATS = {"image", "scan"}


class NormalisedDoc(BaseModel):
    blocks: list[Block]
    source_format: str = "text"
    # Visual and rich documents: line boxes from OCR, images with their alt text, and CSS
    # colours found in HTML emails.
    layout: list[LineBox] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    colours: list[str] = Field(default_factory=list)

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


class Region(BaseModel):
    """A box on a page image, as fractions of the page width and height."""

    page: int = 0
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


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
    # Where on the image the issue is (visual reviews). Findings about the whole asset, such
    # as an off-palette colour or missing alt text, have empty `text` and no span to match.
    region: Region | None = None

    @property
    def document_level(self) -> bool:
        return self.text == ""

    @property
    def rank(self) -> float:
        return SEVERITY_WEIGHT[self.severity] * self.confidence
