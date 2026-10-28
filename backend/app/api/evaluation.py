"""Claim Ledger evaluation: the latest run (precomputed at boot) and on-demand re-runs."""

import json
import logging
import threading
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import get_settings
from app.db import SessionLocal, get_session
from app.engine.claims.ledger import LEDGER_VERSION
from app.engine.context import load_context
from app.eval.run import EVAL_DATE, evaluate, load_items, save
from app.ml.embeddings import get_embedder
from app.ml.nli import get_nli
from app.models import CompileJob, EvalRun, RuleCandidate, User
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


PRECOMPUTED = "precomputed_run.json"


def load_precomputed(session: Session) -> bool:
    """Store the run shipped in data/eval (made with the same models) as the first EvalRun."""
    path = get_settings().data_dir / "eval" / PRECOMPUTED
    if not path.exists():
        return False
    result = json.loads(path.read_text(encoding="utf-8"))
    result["config"] = {**result["config"], "precomputed": True}
    save(session, result)
    return True


def ensure_evaluation() -> None:
    """Called after start-up: make sure judges see results instantly. On slow hosts
    (EVAL_AT_BOOT=precomputed) the shipped run is loaded instead of running 150 claims.
    A latest run made by older verdict logic is replaced the same way; it stays in the list."""
    with SessionLocal() as session:
        latest = session.scalar(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(1))
        if latest is not None and latest.config.get("ledger_version") == LEDGER_VERSION:
            return
        if get_settings().eval_at_boot == "precomputed" and load_precomputed(session):
            return
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


@router.get("/visual")
def visual_evaluation() -> dict[str, Any]:
    """The visual review's evaluation on the 100 labelled assets in data/eval/visual.

    Precomputed with `python -m app.eval.visual --export` (the run's machine and date are in
    the result): a live run reads 100 images with OCR, which would occupy a 0.1-CPU host for
    about ten minutes."""
    path = get_settings().data_dir / "eval" / "visual_run.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No visual evaluation run yet.")
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {**result, "precomputed": True}


@router.get("/compiler")
def compiler_evaluation(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """The Rulebook Compiler against the hand-labelled rules of the sample brand book
    (precomputed with `python -m app.eval.compiler --export`), plus the brand manager's real
    decisions in this workspace: how many accepted candidates needed no edits."""
    path = get_settings().data_dir / "eval" / "compiler_run.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No compiler evaluation run yet.")
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    jobs = select(CompileJob.id).where(CompileJob.workspace_id == user.workspace_id)
    decisions = Counter(
        session.scalars(
            select(RuleCandidate.decision).where(
                RuleCandidate.job_id.in_(jobs), RuleCandidate.decision != "pending"
            )
        )
    )
    accepted = decisions["accepted"] + decisions["edited"]
    result["decisions"] = {
        **{k: decisions[k] for k in ("accepted", "edited", "rejected")},
        "accepted_without_edits": round(decisions["accepted"] / accepted, 3) if accepted else None,
    }
    return {**result, "precomputed": True}


def _precomputed(name: str, missing: str) -> dict[str, Any]:
    path = get_settings().data_dir / "eval" / name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, missing)
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {**result, "precomputed": True}


@router.get("/drafts")
def drafts_evaluation() -> dict[str, Any]:
    """Whole reviews of the 20 labelled full drafts (`python -m app.eval.drafts --export`)."""
    return _precomputed("drafts_run.json", "No full-draft evaluation run yet.")


@router.get("/holdout")
def holdout_evaluation() -> dict[str, Any]:
    """The Claim Ledger on 27 claims written after its Round 3 rules were tuned
    (`python -m app.eval.run --dataset claims_holdout.jsonl --export`)."""
    return _precomputed("claims_holdout_run.json", "No held-out run yet.")
