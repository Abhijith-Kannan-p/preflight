"""Suggest clearer wording for an ambiguous rule.

The hosted LLM sees the rule (title, description, configuration) and the dispute reasons
writers actually gave, and proposes a clearer title and description plus a rationale. When
the LLM is unavailable a deterministic draft states the writers' most common objection as an
explicit exception, and says that it is a draft. Nothing changes until a brand manager edits
and publishes it as a new rule version.
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.ai.gateway import Gateway
from app.ai.masking import Masker


class Rewording(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=1200)
    rationale: str = Field(min_length=10, max_length=1200)


def _prompt(rule: dict[str, Any], reasons: list[str]) -> str:
    quoted = "\n".join(f"- {r}" for r in reasons[:12]) or "(none recorded)"
    return (
        "You are the editor of a company's brand guidelines. Writers keep disputing one rule. "
        "Rewrite the rule so it is unambiguous: say exactly what it covers and what it does "
        "not cover, using the writers' objections below as the cases to clarify. Keep the "
        "rule's intent and strictness; do not weaken it to make disputes go away. Keep the "
        "title under 60 characters and the description under 60 words.\n"
        f"Rule {rule['code']}: {rule['title']}\n"
        f"Description: {rule['description']}\n"
        f"Configuration: {json.dumps(rule.get('config', {}))}\n"
        f"Dispute reasons from writers:\n{quoted}\n"
        'Return JSON: {"title": "...", "description": "...", "rationale": "why this wording '
        'removes the ambiguity, referring to the disputes"}'
    )


def deterministic(rule: dict[str, Any], groups: list[dict[str, Any]]) -> Rewording:
    top = groups[0]["examples"][0] if groups else ""
    exception = (
        f' Writers most often objected: "{top}" State when that case is allowed.' if top else ""
    )
    return Rewording(
        title=rule["title"],
        description=f"{rule['description'].rstrip()}{exception}",
        rationale=(
            "Draft without the LLM (unavailable): the most common dispute reason is quoted so you "
            "can turn it into an explicit exception or a narrower trigger before publishing."
        ),
    )


async def suggest(
    gateway: Gateway, masker: Masker, rule: dict[str, Any], groups: list[dict[str, Any]]
) -> tuple[Rewording, str]:
    """(suggestion, source) where source is "llm" or "deterministic"."""
    reasons = [example for group in groups for example in group["examples"]]
    result = await gateway.complete_json(
        _prompt(rule, reasons), Rewording, purpose="rule_rewording", masker=masker
    )
    if result is not None:
        return result, "llm"
    return deterministic(rule, groups), "deterministic"
