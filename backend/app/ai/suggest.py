"""Intent-preserving suggestions for findings that have no deterministic fix.

Brand-approved wording from the rule (rules.csv `fallback`) is used first. For the rest, one
batched LLM call rewrites only the flagged phrase of each finding, changing as few words as
possible and using only facts from the approved list. Replacements that are much longer
than the phrase, or that introduce a number not found in the original sentence or the
allowed facts, are rejected. Suggestions are never applied automatically.
"""

import re

from pydantic import BaseModel, Field

from app.ai.session import AiSession
from app.engine.claims.quantities import extract
from app.engine.context import ReviewContext
from app.engine.schema import Finding, NormalisedDoc, Suggestion
from app.engine.text import sentence_at

NEEDS_SUGGESTION = {"unsupported_claim", "contradicted_claim", "tone", "readability"}
NO_REWRITE_RULES = {"CLM-08"}
_POSSESSIVE = re.compile(r"^([A-Z]\w*['\u2019]s)\s+")


class Rewrite(BaseModel):
    id: str
    replacement: str = Field(max_length=600)


class Rewrites(BaseModel):
    rewrites: list[Rewrite] = Field(default_factory=list)


def fallback_suggestion(finding: Finding, ctx: ReviewContext) -> str | None:
    rule = ctx.rule(finding.rule.id)
    fallback = rule.config.get("fallback") if rule else None
    if not isinstance(fallback, str):
        return None
    possessive = _POSSESSIVE.match(finding.text)
    return f"{possessive.group(1)} {fallback}" if possessive else fallback


def _allowed_facts(findings: list[Finding], ctx: ReviewContext) -> list[str]:
    ids = {e.fact_id for f in findings for e in f.evidence}
    return [f"{i}: {ctx.facts[i].statement}" for i in sorted(ids) if ctx.facts[i].current]


def _numbers_allowed(replacement: str, sentence: str, facts: list[str]) -> bool:
    allowed = {q.value for text in (sentence, *facts) for q in extract(text)}
    return all(q.value in allowed for q in extract(replacement))


def _prompt(items: list[dict[str, str]], facts: list[str], ctx: ReviewContext) -> str:
    lines = "\n".join(
        f'- id={i["id"]} | rule={i["rule"]} | problem: {i["problem"]}\n'
        f'  sentence: "{i["sentence"]}"\n  phrase to replace: "{i["phrase"]}"'
        for i in items
    )
    fact_lines = "\n".join(facts) or "(none)"
    return (
        "You are a careful brand editor. For each item, write a replacement for the PHRASE "
        "ONLY, so the sentence becomes compliant while keeping the author's intent. Change as "
        "few words as possible and keep the replacement about as long as the phrase. It must "
        "read naturally inside the sentence. Prefer softening or removing the problem over "
        "adding information. If you add information, use only the approved facts below, and "
        "only when they are about the same topic as the phrase. Never invent numbers, awards "
        f"or guarantees.\nApproved facts:\n{fact_lines}\n"
        f"Brand voice: {ctx.voice.get('description', '')}\n"
        f"Items:\n{lines}\n"
        'Return JSON: {"rewrites": [{"id": "...", "replacement": "..."}]}'
    )


async def add_suggestions(
    doc: NormalisedDoc, findings: list[Finding], ctx: ReviewContext, ai: AiSession | None
) -> None:
    # Findings waiting for a human look get no rewrite: a person decides first. "Free" (CLM-08)
    # is fixed by the offer disclaimer that DSC-01 suggests, not by a euphemism.
    pending = [
        f
        for f in findings
        if f.suggestion is None
        and f.type in NEEDS_SUGGESTION
        and not f.needs_review
        and f.rule.id not in NO_REWRITE_RULES
    ]
    # Brand-approved wording from the rulebook wins; the LLM only writes what it lacks.
    for finding in pending:
        fallback = fallback_suggestion(finding, ctx)
        if fallback:
            finding.suggestion = Suggestion(text=fallback)
    pending = [f for f in pending if f.suggestion is None]
    if not pending:
        return
    rewrites: dict[str, str] = {}
    facts = _allowed_facts(pending, ctx)
    if ai is not None and ai.llm_available:
        items = [
            {
                "id": f.id,
                "rule": f.rule.id,
                "problem": f.explanation[:300],
                "sentence": sentence_at(doc.blocks[f.span.block].text, f.span.start).text,
                "phrase": f.text,
            }
            for f in pending
        ]
        result = await ai.gateway.complete_json(
            _prompt(items, facts, ctx), Rewrites, purpose="suggestions", masker=ai.masker,
            log_to=ai.log,
        )  # fmt: skip
        if result is not None:
            rewrites = {r.id: r.replacement.strip() for r in result.rewrites}

    for finding in pending:
        sentence = sentence_at(doc.blocks[finding.span.block].text, finding.span.start).text
        text = rewrites.get(finding.id)
        if (
            text
            and text != finding.text
            and len(text) <= max(2 * len(finding.text) + 20, 40)
            and _numbers_allowed(text, sentence, facts)
        ):
            finding.suggestion = Suggestion(text=text)
