"""Run a review for one revision and persist the results.

Runs in a worker thread with its own event loop so CPU-bound NLI never blocks the API.
Results are cached by (content hash, channel, rulebook version, factbook version).
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.ai.gateway import get_gateway
from app.ai.masking import Masker
from app.ai.session import AiSession
from app.config import get_settings
from app.db import SessionLocal
from app.engine.context import ReviewContext, load_context
from app.engine.pipeline import EventSink, ReviewPlan, ReviewResult, default_checkers, run_review
from app.engine.schema import NormalisedDoc
from app.ml import warmup
from app.ml.embeddings import get_embedder
from app.ml.nli import get_nli
from app.models import AiCall, Claim, Finding, Revision, Severity, Submission, utcnow
from app.seed import WORKSPACE_ID
from app.services.events import TERMINAL, bus

log = logging.getLogger(__name__)

MODEL_WAIT_SECONDS = 120
CARRY_OVER = {"disputed", "escalated"}


def start_review(revision_id: str) -> None:
    """Fire-and-forget: run the review in a background thread."""
    threading.Thread(
        target=run_revision, args=(revision_id,), daemon=True, name=f"review-{revision_id}"
    ).start()


def _emit(revision_id: str) -> EventSink:
    async def emit(event: str, data: dict[str, Any]) -> None:
        bus.publish(revision_id, event, data)

    return emit


def _wait_for_models() -> None:
    if get_settings().skip_model_load:
        return
    deadline = time.monotonic() + MODEL_WAIT_SECONDS
    while not warmup.models_ready() and time.monotonic() < deadline:
        time.sleep(0.5)


# Tests point this at the test database.
session_factory: Callable[[], Session] = SessionLocal


def run_revision(revision_id: str) -> None:
    with session_factory() as session:
        revision = session.get_one(Revision, revision_id)
        submission = session.get_one(Submission, revision.submission_id)
        try:
            ctx = load_context(session, WORKSPACE_ID, submission.channel)
            if _reuse_cached(session, revision, submission, ctx):
                return
            bus.publish(revision_id, "review_started", {"revision": revision.number})
            _wait_for_models()
            embedder, nli = get_embedder(), get_nli()
            masking = bool(ctx.settings.get("masking_enabled", get_settings().masking_enabled))
            ai = AiSession(get_gateway(), Masker(ctx.confidential, enabled=masking))
            plan = default_checkers(nli, embedder, ai)
            doc = NormalisedDoc.model_validate(revision.normalised_doc)
            result = asyncio.run(
                run_review(doc, ctx, plan.checkers, embedder, _emit(revision_id), ai)
            )
            _persist(session, revision, submission, ctx, result, plan, ai, nli, embedder)
        except Exception:
            log.exception("review of %s failed", revision_id)
            session.rollback()
            revision = session.get_one(Revision, revision_id)
            revision.review_status = "failed"
            session.commit()
            bus.publish(
                revision_id,
                TERMINAL,
                {
                    "ok": False,
                    "error": "The review failed. " "Please retry; deterministic checks will run.",
                },
            )
            return
        bus.publish(
            revision_id,
            TERMINAL,
            {"ok": True, "score": revision.brand_score, "degraded": revision.degraded},
        )


def _ai_summary(ai: AiSession, nli_name: str | None, embed_name: str | None) -> dict[str, Any]:
    calls = ai.log.calls
    provider = ai.gateway.provider
    return {
        "mode": ai.gateway.mode,
        "provider": provider.name if provider else None,
        "model": provider.model if provider else None,
        "purposes": sorted({c.purpose for c in calls if c.ok}),
        "failed_purposes": sorted({c.purpose for c in calls if not c.ok}),
        "calls": len(calls),
        "masking_enabled": ai.masker.enabled,
        "masked_count": max((c.masked_count for c in calls), default=0),
        "nli_model": nli_name,
        "embedding_model": embed_name,
    }


def _persist(
    session: Session,
    revision: Revision,
    submission: Submission,
    ctx: ReviewContext,
    result: ReviewResult,
    plan: ReviewPlan,
    ai: AiSession,
    nli: Any,
    embedder: Any,
) -> None:
    previous = _previous_statuses(session, revision)
    for position, f in enumerate(result.findings):
        status = previous.get((f.rule.id, f.text), f.status)
        session.add(
            Finding(
                id=f.id,
                revision_id=revision.id,
                type=f.type,
                span=f.span.model_dump(),
                text=f.text,
                rule_code=f.rule.id,
                rule_source=f.rule.source,
                evidence=[e.model_dump() for e in f.evidence],
                severity=Severity(f.severity),
                confidence=f.confidence,
                explanation=f.explanation,
                suggestion=f.suggestion.model_dump() if f.suggestion else None,
                detector=f.detector,
                status=status if status in CARRY_OVER else f.status,
                needs_review=f.needs_review,
                related=f.related,
                position=position,
            )
        )
    for record in plan.ledger.records:
        session.add(
            Claim(
                revision_id=revision.id,
                text=record.text,
                span=record.span.model_dump(),
                claim_type=record.claim_type,
                verdict=record.verdict,
                fact_id=record.fact_id,
                current_fact_id=record.current_fact_id,
                quote=record.quote,
                scores={**record.scores, "source": record.source},
                confidence=record.confidence,
                steps=record.steps,
            )
        )
    for call in ai.log.calls:
        session.add(
            AiCall(
                revision_id=revision.id,
                purpose=call.purpose,
                provider=call.provider,
                model=call.model,
                latency_ms=call.latency_ms,
                tokens_in=call.tokens_in,
                tokens_out=call.tokens_out,
                masked=call.masked,
                masked_count=call.masked_count,
                ok=call.ok,
                error=call.error,
            )
        )
    revision.report = {
        "checkers": [c.model_dump() for c in result.checkers],
        "score_breakdown": [i.model_dump() for i in result.score.breakdown],
        "tone": plan.tone.profile.model_dump() if plan.tone.profile else None,
        "ai": _ai_summary(ai, getattr(nli, "name", None), getattr(embedder, "name", None)),
    }
    revision.brand_score = result.score.score
    revision.degraded = result.degraded
    revision.review_status = "complete"
    revision.rulebook_version, revision.factbook_version = (
        ctx.rulebook_version,
        ctx.factbook_version,
    )
    revision.completed_at = utcnow()
    audit.record(
        session,
        "revision",
        revision.id,
        "review_completed",
        None,
        {
            "submission": submission.id,
            "number": revision.number,
            "brand_score": result.score.score,
            "findings": len(result.findings),
            "degraded": result.degraded,
        },
    )
    session.commit()


def _previous_statuses(session: Session, revision: Revision) -> dict[tuple[str, str], str]:
    """Disputes and escalations survive a re-check when the same finding reappears."""
    if revision.number <= 1:
        return {}
    prev = session.scalar(
        select(Revision).where(
            Revision.submission_id == revision.submission_id, Revision.number == revision.number - 1
        )
    )
    if prev is None:
        return {}
    rows = session.scalars(select(Finding).where(Finding.revision_id == prev.id))
    return {(f.rule_code, f.text): f.status for f in rows if f.status in CARRY_OVER}


def _reuse_cached(
    session: Session, revision: Revision, submission: Submission, ctx: ReviewContext
) -> bool:
    cached = session.scalar(
        select(Revision)
        .join(Submission, Submission.id == Revision.submission_id)
        .where(
            Revision.content_hash == revision.content_hash,
            Revision.id != revision.id,
            Revision.review_status == "complete",
            Revision.degraded.is_(False),
            Revision.rulebook_version == ctx.rulebook_version,
            Revision.factbook_version == ctx.factbook_version,
            Submission.channel == submission.channel,
        )
        .order_by(Revision.completed_at.desc())
        .limit(1)
    )
    if cached is None:
        return False
    bus.publish(revision.id, "review_started", {"revision": revision.number, "cached": True})
    previous = _previous_statuses(session, revision)
    for f in session.scalars(select(Finding).where(Finding.revision_id == cached.id)):
        status = previous.get((f.rule_code, f.text), "open")
        copy = Finding(
            **{
                c.key: getattr(f, c.key)
                for c in Finding.__table__.columns
                if c.key not in ("id", "revision_id", "status", "applied_text")
            },
            revision_id=revision.id,
            status=status,
        )
        session.add(copy)
    for c in session.scalars(select(Claim).where(Claim.revision_id == cached.id)):
        session.add(
            Claim(
                **{
                    k.key: getattr(c, k.key)
                    for k in Claim.__table__.columns
                    if k.key not in ("id", "revision_id")
                },
                revision_id=revision.id,
            )
        )
    revision.report = {**cached.report, "cached_from": cached.id}
    revision.brand_score, revision.degraded = cached.brand_score, cached.degraded
    revision.rulebook_version, revision.factbook_version = (
        ctx.rulebook_version,
        ctx.factbook_version,
    )
    revision.review_status, revision.completed_at = "complete", utcnow()
    audit.record(
        session,
        "revision",
        revision.id,
        "review_completed",
        None,
        {
            "submission": submission.id,
            "number": revision.number,
            "cached": cached.id,
            "brand_score": cached.brand_score,
        },
    )
    session.commit()
    for checker in revision.report.get("checkers", []):
        bus.publish(revision.id, "checker_done", checker)
    bus.publish(
        revision.id,
        TERMINAL,
        {"ok": True, "score": revision.brand_score, "degraded": revision.degraded, "cached": True},
    )
    return True
