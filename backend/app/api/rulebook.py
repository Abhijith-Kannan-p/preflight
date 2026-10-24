"""Read endpoints for the Brand Knowledge Base. Editing arrives with roles and permissions."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    ChannelProfile,
    ConfidentialTerm,
    Fact,
    Rule,
    RuleStatus,
    SampleDraft,
    Term,
    User,
    Workspace,
)
from app.schemas.rulebook import (
    ChannelOut,
    ConfidentialTermOut,
    FactOut,
    RuleOut,
    SampleDraftOut,
    TermOut,
    UserOut,
    VoiceProfileOut,
)
from app.seed import WORKSPACE_ID

router = APIRouter(prefix="/api", tags=["rulebook"])


@router.get("/users", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return list(session.scalars(select(User).order_by(User.id)))


@router.get("/rulebook/rules", response_model=list[RuleOut])
def list_rules(
    include_retired: bool = False, session: Session = Depends(get_session)
) -> list[Rule]:
    query = select(Rule).order_by(Rule.code, Rule.version.desc())
    if not include_retired:
        query = query.where(Rule.status != RuleStatus.retired)
    return list(session.scalars(query))


@router.get("/rulebook/facts", response_model=list[FactOut])
def list_facts(session: Session = Depends(get_session)) -> list[FactOut]:
    today = date.today()
    facts = session.scalars(select(Fact).order_by(Fact.id))
    return [
        FactOut.model_validate(
            {**_columns(f), "source_ref": f.source_ref, "is_current": f.is_current(today)}
        )
        for f in facts
    ]


@router.get("/rulebook/terms", response_model=list[TermOut])
def list_terms(session: Session = Depends(get_session)) -> list[Term]:
    return list(session.scalars(select(Term).order_by(Term.kind, Term.term)))


@router.get("/rulebook/channels", response_model=list[ChannelOut])
def list_channels(session: Session = Depends(get_session)) -> list[ChannelProfile]:
    return list(session.scalars(select(ChannelProfile).order_by(ChannelProfile.name)))


@router.get("/rulebook/confidential", response_model=list[ConfidentialTermOut])
def list_confidential(session: Session = Depends(get_session)) -> list[ConfidentialTerm]:
    return list(session.scalars(select(ConfidentialTerm).order_by(ConfidentialTerm.term)))


@router.get("/rulebook/voice", response_model=VoiceProfileOut)
def voice_profile(session: Session = Depends(get_session)) -> VoiceProfileOut:
    workspace = session.get_one(Workspace, WORKSPACE_ID)
    return VoiceProfileOut.model_validate(workspace.voice_profile)


@router.get("/samples", response_model=list[SampleDraftOut])
def list_samples(session: Session = Depends(get_session)) -> list[SampleDraft]:
    return list(session.scalars(select(SampleDraft).order_by(SampleDraft.position)))


def _columns(fact: Fact) -> dict[str, object]:
    return {c.key: getattr(fact, c.key) for c in Fact.__table__.columns if c.key != "embedding"}
