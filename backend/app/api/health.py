"""Health endpoint used by the frontend "Waking up the engine..." state and hosting probes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import db
from app.config import get_settings
from app.ml import warmup

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "starting"]
    database: bool
    models_ready: bool
    embedding_model: str | None
    nli_model: str | None
    llm_provider: str
    version: str


def _name(value: str | float | None) -> str | None:
    return value if isinstance(value, str) else None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_ok = db.database_reachable()
    ready = warmup.models_ready()
    models = warmup.model_status()
    status: Literal["ok", "degraded", "starting"] = (
        "degraded" if not database_ok else "ok" if ready else "starting"
    )
    return HealthResponse(
        status=status,
        database=database_ok,
        models_ready=ready,
        embedding_model=_name(models["embedder"]),
        nli_model=_name(models["nli"]),
        llm_provider=get_settings().llm_provider,
        version="0.2.0",
    )
