"""The typed rule schema the Rulebook Compiler produces.

Every candidate is one of these kinds, each mapped to something the review engine executes:

- term: term, variants, note → a product name (TRM-02)
- word: term, status (banned or discouraged), replacement → a TRM-05 word
- pattern: rule (CLM-01/04/06/08), pattern → a new version of that claim rule
- disclaimer: title, triggers, disclaimer, severity → a new or updated DSC rule
- colour: name, hex → a brand palette colour (VIS-01)
- channel: channel, max_chars, max_hashtags, subject_max_chars → the channel's limits
- threshold: rule (TON-03/RDB-01), field, value → a new version of that rule
- voice: five 0-1 trait targets → the voice profile (TON-01)
- guidance: category, title, description, severity → a cited rule checked by people

`key` identifies a candidate for de-duplication and for the accuracy evaluation.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

Kind = Literal[
    "term", "word", "pattern", "disclaimer", "colour", "channel", "threshold", "voice", "guidance"
]
Severity = Literal["critical", "major", "minor"]

PATTERN_RULES = {"CLM-01", "CLM-04", "CLM-06", "CLM-08"}
THRESHOLDS = {
    "TON-03": {"max_exclamations_per_100_words", "max_caps_word_length"},
    "RDB-01": {"min_flesch", "max_sentence_words"},
}
CHANNELS = {"linkedin", "x", "email", "press_release", "blog"}
CATEGORIES = {
    "claims",
    "terminology",
    "tone",
    "disclaimer",
    "channel",
    "readability",
    "visual",
    "accessibility",
}


class TermPayload(BaseModel):
    term: str = Field(min_length=2, max_length=80)
    variants: list[str] = Field(default_factory=list)
    note: str = ""


class WordPayload(BaseModel):
    term: str = Field(min_length=2, max_length=80)
    status: Literal["banned", "discouraged"]
    replacement: str | None = None

    @field_validator("replacement")
    @classmethod
    def blank_is_none(cls, v: str | None) -> str | None:
        return None if v is None or v.strip() in ("", "-") else v.strip()


class PatternPayload(BaseModel):
    rule: str
    pattern: str = Field(min_length=1, max_length=60)

    @field_validator("rule")
    @classmethod
    def known_rule(cls, v: str) -> str:
        if v not in PATTERN_RULES:
            raise ValueError(f"pattern rules are {sorted(PATTERN_RULES)}")
        return v


class DisclaimerPayload(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    triggers: list[str] = Field(min_length=1)
    disclaimer: str = Field(min_length=3, max_length=200)
    severity: Severity = "major"


class ColourPayload(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    hex: str

    @field_validator("hex")
    @classmethod
    def hex_colour(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v.strip()):
            raise ValueError("hex must be #RRGGBB")
        return v.strip().upper()


class ChannelPayload(BaseModel):
    channel: str
    max_chars: int | None = Field(default=None, ge=1)
    max_hashtags: int | None = Field(default=None, ge=0)
    subject_max_chars: int | None = Field(default=None, ge=1)

    @field_validator("channel")
    @classmethod
    def known_channel(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in CHANNELS:
            raise ValueError(f"channel must be one of {sorted(CHANNELS)}")
        return v


class ThresholdPayload(BaseModel):
    rule: str
    field: str
    value: float

    @field_validator("field")
    @classmethod
    def known_field(cls, v: str) -> str:
        if not any(v in fields for fields in THRESHOLDS.values()):
            raise ValueError("unknown threshold")
        return v


class VoicePayload(BaseModel):
    traits: dict[str, float]

    @field_validator("traits")
    @classmethod
    def five_traits(cls, v: dict[str, float]) -> dict[str, float]:
        wanted = {"formal", "warm", "confident", "playful", "technical"}
        if set(v) != wanted or not all(0 <= x <= 1 for x in v.values()):
            raise ValueError("five traits, each 0 to 1")
        return v


class GuidancePayload(BaseModel):
    category: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=1200)
    severity: Severity = "major"

    @field_validator("category")
    @classmethod
    def known_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
        return v


PAYLOADS: dict[str, type[BaseModel]] = {
    "term": TermPayload,
    "word": WordPayload,
    "pattern": PatternPayload,
    "disclaimer": DisclaimerPayload,
    "colour": ColourPayload,
    "channel": ChannelPayload,
    "threshold": ThresholdPayload,
    "voice": VoicePayload,
    "guidance": GuidancePayload,
}


class Candidate(BaseModel):
    kind: Kind
    payload: dict[str, Any]
    source_page: int = Field(ge=1)
    excerpt: str = ""
    origin: Literal["deterministic", "llm"] = "deterministic"

    @property
    def key(self) -> str:
        return candidate_key(self.kind, self.payload, self.source_page)


def candidate_key(kind: str, p: dict[str, Any], page: int) -> str:
    if kind in ("term", "word"):
        return f"{kind}:{str(p['term']).lower()}"
    if kind == "pattern":
        return f"pattern:{p['rule']}:{str(p['pattern']).lower()}"
    if kind == "disclaimer":
        return f"disclaimer:{str(p['disclaimer']).lower().rstrip('.')}"
    if kind == "colour":
        return f"colour:{p['hex']}"
    if kind == "channel":
        return f"channel:{p['channel']}"
    if kind == "threshold":
        return f"threshold:{p['rule']}:{p['field']}"
    if kind == "voice":
        return "voice"
    slug = re.sub(r"[^a-z0-9]+", "-", str(p.get("title", "")).lower()).strip("-")[:40]
    return f"guidance:p{page}:{slug}"


def validate(kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The payload normalised by its schema, or None if it does not fit."""
    model = PAYLOADS.get(kind)
    if model is None:
        return None
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError:
        return None
