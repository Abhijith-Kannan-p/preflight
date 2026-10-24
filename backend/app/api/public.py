"""Public REST API for CMSs and pipelines: POST /api/v1/preflight with an X-API-Key header.

Runs the same review engine synchronously (in a worker thread) and returns the findings,
the Claim Ledger and the Brand Score. Nothing is stored except the API key's last-used time.
"""

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import get_gateway
from app.ai.masking import Masker
from app.ai.session import AiSession
from app.api.settings import hash_key
from app.config import get_settings
from app.db import get_session
from app.engine.context import load_context
from app.engine.normalise import IntakeError, from_text, from_upload
from app.engine.pipeline import default_checkers, run_review
from app.engine.schema import Finding, NormalisedDoc
from app.engine.score import BrandScore
from app.ml.embeddings import get_embedder
from app.ml.nli import get_nli
from app.models import ApiKey, ChannelProfile, utcnow
from app.seed import WORKSPACE_ID
from app.services.ratelimit import RateLimiter

router = APIRouter(prefix="/api/v1", tags=["public API"])
limiter = RateLimiter(limit=30, window_seconds=60)


class PreflightRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000, description="Plain text or Markdown")
    channel: Literal["linkedin", "x", "email", "press_release", "blog"] = "linkedin"


class LedgerEntry(BaseModel):
    text: str
    verdict: str
    fact_id: str | None
    current_fact_id: str | None
    quote: str | None
    confidence: float


class PreflightResponse(BaseModel):
    brand_score: BrandScore
    blocking: bool = Field(description="True if any critical finding is open")
    findings: list[Finding]
    claims: list[LedgerEntry]
    degraded: bool
    blocks: list[dict[str, Any]]


def api_key(
    request: Request,
    x_api_key: str = Header(..., description="Create one in Settings → API keys"),
    session: Session = Depends(get_session),
) -> ApiKey:
    key = session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(x_api_key)))
    if key is None or key.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key.")
    allowed, retry = limiter.allow(key.id)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit: 30 requests per minute.",
            headers={"Retry-After": str(int(retry) + 1)},
        )
    key.last_used_at = utcnow()
    session.commit()
    return key


async def _review(doc: NormalisedDoc, channel: str, session: Session) -> PreflightResponse:
    if session.get(ChannelProfile, channel) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown channel {channel}.")
    ctx = load_context(session, WORKSPACE_ID, channel)

    def run() -> PreflightResponse:
        embedder, nli = get_embedder(), get_nli()
        masking = bool(ctx.settings.get("masking_enabled", get_settings().masking_enabled))
        ai = AiSession(get_gateway(), Masker(ctx.confidential, enabled=masking))
        plan = default_checkers(nli, embedder, ai)
        result = asyncio.run(run_review(doc, ctx, plan.checkers, embedder, ai=ai))
        return PreflightResponse(
            brand_score=result.score,
            blocking=any(f.severity == "critical" and not f.needs_review for f in result.findings),
            findings=result.findings,
            claims=[
                LedgerEntry(
                    **r.model_dump(
                        include={
                            "text",
                            "verdict",
                            "fact_id",
                            "current_fact_id",
                            "quote",
                            "confidence",
                        }
                    )
                )
                for r in plan.ledger.records
            ],
            degraded=result.degraded,
            blocks=[b.model_dump() for b in doc.blocks],
        )

    return await asyncio.to_thread(run)


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(
    body: PreflightRequest, key: ApiKey = Depends(api_key), session: Session = Depends(get_session)
) -> PreflightResponse:
    """Check a draft before publishing. Use `blocking` to stop a CMS publish step."""
    try:
        doc = from_text(body.content, markdown=body.content.lstrip().startswith("#"))
    except IntakeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _review(doc, body.channel, session)


@router.post("/preflight/file", response_model=PreflightResponse)
async def preflight_file(
    request: Request, key: ApiKey = Depends(api_key), session: Session = Depends(get_session)
) -> PreflightResponse:
    """Same as /preflight for a DOCX, PDF, TXT or MD upload (multipart field `file`,
    optional form field `channel`)."""
    form = await request.form()
    upload = form.get("file")
    channel = str(form.get("channel") or "linkedin")
    if upload is None or isinstance(upload, str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send the file in field 'file'.")
    try:
        doc = from_upload(upload.filename or "upload.txt", await upload.read(5 * 1024 * 1024 + 1))
    except IntakeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _review(doc, channel, session)
