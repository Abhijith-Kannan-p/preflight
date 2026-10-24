"""Review pipeline: run checkers concurrently, validate, merge, attach drift, score.

Progress is reported through an async callback so the API can stream it over SSE.
A checker that fails is reported as `degraded`; the others still finish.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.claims import llm_extractor
from app.ai.session import AiSession
from app.ai.suggest import add_suggestions
from app.engine.checkers.base import Checker
from app.engine.checkers.channel import ChannelChecker
from app.engine.checkers.disclaimer import DisclaimerChecker
from app.engine.checkers.readability import ReadabilityChecker
from app.engine.checkers.style import StyleChecker
from app.engine.checkers.terminology import TerminologyChecker
from app.engine.checkers.tone import ToneChecker
from app.engine.claims.ledger import ClaimExtractor, ClaimLedger
from app.engine.context import ReviewContext
from app.engine.drift import attach_drift
from app.engine.merge import merge_findings
from app.engine.schema import Finding, NormalisedDoc
from app.engine.score import BrandScore, brand_score
from app.engine.validate import valid_findings
from app.ml.embeddings import Embedder
from app.ml.nli import NliModel

log = logging.getLogger(__name__)

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


async def _ignore(_event: str, _data: dict[str, Any]) -> None:
    return None


class CheckerRun(BaseModel):
    name: str
    label: str
    ok: bool
    findings: int
    ms: int
    error: str | None = None


class ReviewResult(BaseModel):
    findings: list[Finding]
    score: BrandScore
    checkers: list[CheckerRun]
    degraded: bool


@dataclass
class ReviewPlan:
    """The checkers for one review, keeping handles to those with extra outputs."""

    checkers: list[Checker]
    ledger: ClaimLedger
    tone: ToneChecker


def default_checkers(
    nli: NliModel | None,
    embedder: Embedder | None,
    ai: AiSession | None = None,
    extractor: ClaimExtractor | None = None,
) -> ReviewPlan:
    """All Round 2 checkers. With an AI session, claims are also extracted by the LLM."""
    if extractor is None and ai is not None:
        extractor = llm_extractor(ai)
    ledger = ClaimLedger(nli, embedder, extractor)
    tone = ToneChecker(ai)
    return ReviewPlan([*deterministic_checkers(), tone, ledger], ledger, tone)


def deterministic_checkers() -> list[Checker]:
    return [
        TerminologyChecker(),
        DisclaimerChecker(),
        ChannelChecker(),
        ReadabilityChecker(),
        StyleChecker(),
    ]


async def run_review(
    doc: NormalisedDoc,
    ctx: ReviewContext,
    checkers: Sequence[Checker],
    embedder: Embedder | None = None,
    emit: EventSink = _ignore,
    ai: AiSession | None = None,
) -> ReviewResult:
    async def run_one(checker: Checker) -> tuple[CheckerRun, list[Finding]]:
        await emit("checker_started", {"checker": checker.name, "label": checker.label})
        started = time.perf_counter()
        try:
            found = valid_findings(await checker.run(doc, ctx), doc, ctx)
            run = CheckerRun(
                name=checker.name,
                label=checker.label,
                ok=True,
                findings=len(found),
                ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            log.exception("checker %s failed", checker.name)
            found = []
            run = CheckerRun(
                name=checker.name,
                label=checker.label,
                ok=False,
                findings=0,
                ms=int((time.perf_counter() - started) * 1000),
                error=type(exc).__name__,
            )
            await emit("degraded", {"checker": checker.name, "reason": run.error})
        for finding in found:
            await emit("finding", finding.model_dump())
        await emit("checker_done", run.model_dump())
        return run, found

    results = await asyncio.gather(*(run_one(c) for c in checkers))
    runs = [r for r, _ in results]
    findings = merge_findings([f for _, found in results for f in found])
    await emit("checker_started", {"checker": "suggestions", "label": "Suggestions"})
    started = time.perf_counter()
    await add_suggestions(doc, findings, ctx, ai)
    attach_drift(doc, findings, embedder)
    await emit(
        "checker_done",
        CheckerRun(name="suggestions", label="Suggestions", ok=True,
                   findings=sum(f.suggestion is not None for f in findings),
                   ms=int((time.perf_counter() - started) * 1000)).model_dump(),
    )  # fmt: skip
    # AI is "limited" when a hosted LLM is configured but a call failed or the breaker is open.
    ai_limited = (
        ai is not None
        and ai.gateway.provider is not None
        and (not ai.gateway.available or any(not c.ok for c in ai.log.calls))
    )
    if ai_limited:
        await emit("degraded", {"checker": "ai", "reason": "AI checks temporarily limited"})
    return ReviewResult(
        findings=findings,
        score=brand_score(findings),
        checkers=runs,
        degraded=ai_limited or not all(r.ok for r in runs),
    )
