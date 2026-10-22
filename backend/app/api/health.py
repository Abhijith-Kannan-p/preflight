"""Health endpoint used by the frontend "Waking up the engine..." state and hosting probes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import db
from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    llm_provider: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_ok = db.database_reachable()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        database=database_ok,
        llm_provider=get_settings().llm_provider,
        version="0.1.0",
    )
