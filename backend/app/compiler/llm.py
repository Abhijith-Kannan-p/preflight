"""LLM extraction for the prose parts of a brand book.

One call with the page texts (numbered) asks for candidates in the typed rule schema. Every
item is validated with the same payload models as deterministic candidates; anything that
does not fit is dropped and counted. The LLM never activates anything: candidates wait in the
review queue for a brand manager.
"""

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.ai.gateway import Gateway, build_provider
from app.ai.masking import Masker
from app.compiler.extract import Page
from app.compiler.schema import CATEGORIES, CHANNELS, PATTERN_RULES, THRESHOLDS, Candidate, validate
from app.config import get_settings

COMPILER_TIMEOUT_SECONDS = 40.0
MAX_CHARS = 14_000


class RawCandidate(BaseModel):
    kind: str
    page: int = Field(ge=1)
    excerpt: str = ""
    payload: dict[str, Any]


class RawCandidates(BaseModel):
    # Items are checked one by one, so one malformed item does not sink the whole answer.
    candidates: list[dict[str, Any]] = Field(default_factory=list)


def _item(raw: dict[str, Any]) -> RawCandidate | None:
    if "payload" not in raw:  # payload fields written at the top level
        meta = {"kind", "page", "excerpt"}
        raw = {
            **{k: v for k, v in raw.items() if k in meta},
            "payload": {k: v for k, v in raw.items() if k not in meta},
        }
    try:
        return RawCandidate.model_validate(raw)
    except ValidationError:
        return None


def _prompt(pages: list[Page]) -> str:
    text = "\n\n".join(f"[page {p.number}] {p.title}\n{p.text}" for p in pages if p.text)[
        :MAX_CHARS
    ]
    schema = {
        "pattern": {
            "rule": f"one of {sorted(PATTERN_RULES)}",
            "pattern": "a phrase writers must not use",
        },
        "disclaimer": {
            "title": "short name",
            "triggers": ["lowercase words or phrases that require it"],
            "disclaimer": "the exact required text",
            "severity": "critical|major|minor",
        },
        "threshold": {
            "rule": f"one of {sorted(THRESHOLDS)}",
            "field": f"one of {THRESHOLDS}",
            "value": 0,
        },
        "channel": {
            "channel": f"one of {sorted(CHANNELS)}",
            "max_chars": 0,
            "max_hashtags": 0,
            "subject_max_chars": 0,
        },
        "guidance": {
            "category": "|".join(sorted(CATEGORIES)),
            "title": "short rule title",
            "description": "the rule in one or two sentences",
            "severity": "critical|major|minor",
        },
    }
    return (
        "You compile a company brand book into machine-checkable rules. From the pages below, "
        "extract every rule as a candidate of one of these kinds (payload shapes given):\n"
        f"{json.dumps(schema, indent=1)}\n"
        "Use 'pattern' for each specific phrase the book forbids in claims (CLM-01 superlatives, "
        "CLM-04 absolute security or safety, CLM-06 guaranteed outcomes, CLM-08 'free'). Use "
        "'disclaimer' when the book requires exact text for certain words, listing every trigger "
        "word it names. Use 'guidance' for any other rule a reviewer should follow (facts, logo, "
        "accessibility, palette). Quote only what the book says; never invent rules or numbers. "
        "Cite the page each rule is on and copy the sentence as 'excerpt'.\n\n"
        f"{text}\n\n"
        'Return JSON: {"candidates": [{"kind": "...", "page": 1, "excerpt": "...", '
        '"payload": {...}}]}'
    )


def compiler_gateway() -> Gateway:
    """The usual provider with a longer timeout: one call reads the whole book."""
    return Gateway(build_provider(get_settings()), timeout=COMPILER_TIMEOUT_SECONDS)


async def extract(
    pages: list[Page], gateway: Gateway, masker: Masker
) -> tuple[list[Candidate], dict[str, Any]]:
    """(valid candidates, report). The report says whether the LLM ran and what was dropped."""
    if gateway.provider is None:
        return [], {"llm": "not configured", "returned": 0, "dropped": 0}
    raw = await gateway.complete_json(
        _prompt(pages), RawCandidates, purpose="rule_compiler", masker=masker
    )
    if raw is None:
        return [], {"llm": "failed", "returned": 0, "dropped": 0}
    numbers = {p.number for p in pages}
    found: list[Candidate] = []
    dropped = 0
    for entry in raw.candidates:
        item = _item(entry)
        payload = validate(item.kind, item.payload) if item else None
        if item is None or payload is None or item.page not in numbers:
            dropped += 1
            continue
        found.append(
            Candidate(
                kind=item.kind,
                payload=payload,
                source_page=item.page,
                excerpt=item.excerpt[:400],
                origin="llm",
            )
        )
    return found, {"llm": "ok", "returned": len(raw.candidates), "dropped": dropped}
