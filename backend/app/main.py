"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    evaluation,
    health,
    insights,
    public,
    receipts,
    reviews,
    rulebook,
    rulebook_edit,
    session,
)
from app.api import settings as settings_api
from app.config import get_settings
from app.ml.warmup import start_warmup


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Load models in the background (/health reports when ready), then prepare the demo.
    start_warmup(after=bootstrap if get_settings().bootstrap_demo else None)
    yield


def bootstrap() -> None:
    from app.api.evaluation import ensure_evaluation
    from app.services.history import ensure_demo_history

    ensure_demo_history()
    ensure_evaluation()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Preflight API",
        description="Content cleared before it goes live. Pre-publication brand governance.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(rulebook.router)
    app.include_router(rulebook_edit.router)
    app.include_router(session.router)
    app.include_router(reviews.router)
    app.include_router(receipts.router)
    app.include_router(insights.router)
    app.include_router(evaluation.router)
    app.include_router(settings_api.router)
    app.include_router(public.router)
    return app


app = create_app()
