"""Governance intelligence: Guideline Health, the Stale-Content Radar and the Creator Coach."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.ai.gateway import get_gateway
from app.ai.masking import Masker
from app.api.rulebook_edit import supersede_fact
from app.auth import Permission, current_user, require
from app.db import get_session
from app.engine.normalise import from_text
from app.governance import coach, health, radar, reword
from app.models import (
    ConfidentialTerm,
    Revision,
    Rule,
    RuleStatus,
    Submission,
    User,
    Workspace,
)
from app.schemas.rulebook import SupersedeIn
from app.scoped import get_fact
from app.services import runner

router = APIRouter(prefix="/api", tags=["governance"])

SIMULATED_FACT = {
    "statement": "PayWise settles merchant payments in under 15 seconds.",
    "source_doc": "ops_sla_2026_q4.pdf (simulated)",
}


# --- Guideline Health -------------------------------------------------------------------


@router.get("/governance/health")
def guideline_health(
    days: int = Query(health.WINDOW_DAYS, ge=7, le=365),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Per-rule dispute, override and acceptance rates, the ambiguity score, grouped dispute
    reasons and metrics per rule version."""
    return health.compute(session, user.workspace_id, days)


class RewordingOut(BaseModel):
    code: str
    version: int
    title: str
    description: str
    rationale: str
    source: str
    config: dict[str, Any]


@router.post("/governance/rules/{code}/suggest", response_model=RewordingOut)
async def suggest_rewording(
    code: str,
    user: User = Depends(require(Permission.edit_rulebook)),
    session: Session = Depends(get_session),
) -> RewordingOut:
    """A clearer wording for a disputed rule, written from the actual dispute reasons. Nothing
    changes until the brand manager publishes it (PUT /api/rulebook/rules/{code})."""
    rule = session.scalar(
        select(Rule).where(
            Rule.workspace_id == user.workspace_id,
            Rule.code == code,
            Rule.status == RuleStatus.active,
        )
    )
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No active rule {code}.")
    report = next(
        r for r in health.compute(session, user.workspace_id)["rules"] if r["code"] == code
    )
    confidential = session.scalars(
        select(ConfidentialTerm.term).where(ConfidentialTerm.workspace_id == user.workspace_id)
    ).all()
    workspace = session.get_one(Workspace, user.workspace_id)
    masker = Masker(
        tuple(confidential), enabled=bool(workspace.settings.get("masking_enabled", True))
    )
    data = {
        "code": code,
        "title": rule.title,
        "description": rule.description,
        "config": rule.config,
    }
    suggestion, source = await reword.suggest(get_gateway(), masker, data, report["reason_groups"])
    return RewordingOut(
        code=code,
        version=rule.version,
        title=suggestion.title,
        description=suggestion.description,
        rationale=suggestion.rationale,
        source=source,
        config=rule.config,
    )


# --- Stale-Content Radar ----------------------------------------------------------------


@router.get("/radar")
def stale_content(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    dependencies = radar.dependencies(session, user.workspace_id)
    return {
        "indexed_items": len({d.submission_id for d in dependencies}),
        "indexed_dependencies": len(dependencies),
        "facts_relied_on": sorted({d.fact_id for d in dependencies}),
        "entries": radar.stale(session, user.workspace_id),
    }


@router.post("/radar/simulate", status_code=201)
def simulate_fact_update(
    user: User = Depends(require(Permission.edit_rulebook)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Demo: supersede F-087 (settlement in under 10 seconds) with a new fact, in your own
    demo workspace, exactly as editing the fact in the Rulebook would."""
    current = get_fact(session, user.workspace_id, "F-087")
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "F-087 is not in this workspace.")
    if current.superseded_by:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"F-087 is already superseded by {current.superseded_by}. Reset your demo workspace "
            "to simulate again.",
        )
    new_id = next(
        f"F-{n:03d}"
        for n in range(88, 999)
        if get_fact(session, user.workspace_id, f"F-{n:03d}") is None
    )
    body = SupersedeIn(new_id=new_id, valid_from=date.today(), source_page=1, **SIMULATED_FACT)
    return supersede_fact("F-087", body, user, session)


@router.post("/radar/{review_id}/recheck", status_code=201)
def recheck_stale(
    review_id: str,
    user: User = Depends(require(Permission.submit_content)),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Open the cleared text as a new review, checked against today's facts."""
    submission = session.get(Submission, review_id)
    if submission is None or submission.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found.")
    cleared = session.scalar(
        select(Revision)
        .where(Revision.submission_id == review_id)
        .order_by(Revision.number.desc())
        .limit(1)
    )
    if cleared is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review has no text.")
    from app.api.reviews import _new_revision

    doc = from_text(cleared.content)
    new = Submission(
        workspace_id=user.workspace_id,
        author_id=user.id,
        channel=submission.channel,
        title=f"{submission.title} (re-check after a fact change)"[:200],
    )
    session.add(new)
    session.flush()
    revision = _new_revision(session, new, doc, user, 1, f"re-check of {review_id}")
    audit.record(
        session,
        "submission",
        new.id,
        "created",
        user.id,
        {"title": new.title, "recheck_of": review_id, "revision": revision.id},
    )
    session.commit()
    runner.start_review(revision.id)
    return {"id": new.id, "revision_id": revision.id}


# --- Creator Coach ----------------------------------------------------------------------


@router.get("/coach/me")
def my_coach(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    return coach.profile(session, user.workspace_id, user)


@router.get("/coach")
def team_coach(
    user: User = Depends(require(Permission.view_insights)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return coach.team(session, user.workspace_id)
