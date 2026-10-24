"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, reviews, rulebook, session
from app.config import get_settings
from app.ml.warmup import start_warmup


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_warmup()  # loads models in the background; /health reports when ready
    yield


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
    app.include_router(session.router)
    app.include_router(reviews.router)
    return app


app = create_app()
