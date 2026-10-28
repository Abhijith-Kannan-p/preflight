"""FastAPI application entry point."""

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    evaluation,
    health,
    insights,
    public,
    receipts,
    reviews,
    rulebook,
    rulebook_edit,
    sandbox,
    session,
)
from app.api import settings as settings_api
from app.config import get_settings
from app.idempotency import IdempotencyMiddleware
from app.ml.warmup import start_warmup


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Load models in the background (/health reports when ready), then prepare the demo.
    start_warmup(after=bootstrap if get_settings().bootstrap_demo else None)
    yield


def bootstrap() -> None:
    from app.api.evaluation import ensure_evaluation
    from app.services.history import ensure_demo_history
    from app.services.runner import resume_pending
    from app.services.sandbox import start_sweeper

    # Evaluation first: when precomputed it is instant, so the page is ready immediately even
    # while the history is still being generated on a slow host.
    # Reviews interrupted by a restart are queued again, so a reloaded page reattaches.
    resume_pending()
    ensure_evaluation()
    ensure_demo_history()
    start_sweeper()


log = logging.getLogger("app")


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log the details; show the visitor a plain message and a reference, never a trace."""
    request_id = secrets.token_hex(4)
    log.error(
        "unhandled error %s on %s %s", request_id, request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        {
            "detail": "Something went wrong on our side. Please try again; if it keeps "
            f"happening, mention reference {request_id}.",
            "request_id": request_id,
        },
        status_code=500,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Preflight API",
        description="Content cleared before it goes live. Pre-publication brand governance.",
        version="0.2.0",
        lifespan=lifespan,
    )
    # Added first, so CORS wraps it and replayed responses still carry CORS headers.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotent-Replayed"],
    )
    app.add_exception_handler(Exception, _unexpected_error)
    app.include_router(health.router)
    app.include_router(rulebook.router)
    app.include_router(rulebook_edit.router)
    app.include_router(session.router)
    app.include_router(sandbox.router)
    app.include_router(reviews.router)
    app.include_router(receipts.router)
    app.include_router(insights.router)
    app.include_router(evaluation.router)
    app.include_router(settings_api.router)
    app.include_router(public.router)
    return app


app = create_app()
