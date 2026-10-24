"""Review pipeline: run checkers concurrently, validate, merge, attach drift, score.

Progress is reported through an async callback so the API can stream it over SSE.
A checker that fails is reported as `degraded`; the others still finish.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel

from app.engine.checkers.base import Checker
from app.engine.checkers.channel import ChannelChecker
from app.engine.checkers.disclaimer import DisclaimerChecker
from app.engine.checkers.readability import ReadabilityChecker
from app.engine.checkers.style import StyleChecker
from app.engine.checkers.terminology import TerminologyChecker
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


def default_checkers(
    nli: NliModel | None,
    embedder: Embedder | None,
    extractor: ClaimExtractor | None = None,
) -> tuple[list[Checker], ClaimLedger]:
    """All Round 2 checkers. The ledger is returned too, so callers can read its records."""
    ledger = ClaimLedger(nli, embedder, extractor)
    return [*deterministic_checkers(), ledger], ledger


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
    attach_drift(doc, findings, embedder)
    return ReviewResult(
        findings=findings,
        score=brand_score(findings),
        checkers=runs,
        degraded=not all(r.ok for r in runs),
    )
