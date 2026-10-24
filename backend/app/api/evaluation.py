"""Claim Ledger evaluation: the latest run (precomputed at boot) and on-demand re-runs."""

import logging
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import get_settings
from app.db import SessionLocal, get_session
from app.engine.context import load_context
from app.eval.run import EVAL_DATE, evaluate, load_items, save
from app.ml.embeddings import get_embedder
from app.ml.nli import get_nli
from app.models import EvalRun, User
from app.seed import WORKSPACE_ID

router = APIRouter(prefix="/api/eval", tags=["evaluation"])
log = logging.getLogger(__name__)
_running = threading.Lock()


class EvalRunOut(BaseModel):
    id: str
    created_at: datetime
    n_items: int
    metrics: dict[str, Any]
    confusion: dict[str, Any]
    failures: list[Any]
    latency_ms_p50: float
    latency_ms_p95: float
    config: dict[str, Any]


class EvalStatus(BaseModel):
    running: bool
    latest: EvalRunOut | None
    runs: list[dict[str, Any]]


def run_evaluation() -> None:
    """Run the labelled set once; skipped if a run is already in progress."""
    if not _running.acquire(blocking=False):
        return
    try:
        items = load_items(get_settings().data_dir / "eval" / "claims.jsonl")
        with SessionLocal() as session:
            ctx = load_context(session, WORKSPACE_ID, "blog", today=EVAL_DATE)
            save(session, evaluate(items, ctx, get_nli(), get_embedder()))
    except Exception:
        log.exception("evaluation run failed")
    finally:
        _running.release()


def ensure_evaluation() -> None:
    """Called after models warm up: make sure judges see results instantly."""
    with SessionLocal() as session:
        if session.scalar(select(EvalRun.id).limit(1)) is None:
            run_evaluation()


@router.get("", response_model=EvalStatus)
def latest(session: Session = Depends(get_session)) -> EvalStatus:
    runs = list(session.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(10)))
    return EvalStatus(
        running=_running.locked(),
        latest=EvalRunOut.model_validate(runs[0], from_attributes=True) if runs else None,
        runs=[
            {
                "id": r.id,
                "created_at": r.created_at,
                "accuracy": r.metrics.get("accuracy"),
                "macro_recall": r.metrics.get("macro_recall"),
            }
            for r in runs
        ],
    )


@router.post("/run", status_code=202)
def start_run(user: User = Depends(current_user)) -> dict[str, str]:
    if _running.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "An evaluation is already running.")
    threading.Thread(target=run_evaluation, daemon=True, name="evaluation").start()
    return {"status": "started"}
