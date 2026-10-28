from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Fact, Rule, Term, User, Workspace
from app.scoped import get_fact
from app.seed import WORKSPACE_ID, seed_all
from tests.fakes import HashingEmbedder


def _counts(session: Session) -> tuple[int, int, int, int]:
    return (
        session.scalar(select(func.count()).select_from(Rule)) or 0,
        session.scalar(select(func.count()).select_from(Fact)) or 0,
        session.scalar(select(func.count()).select_from(Term)) or 0,
        session.scalar(select(func.count()).select_from(User)) or 0,
    )


def test_seed_is_idempotent(session: Session) -> None:
    before = _counts(session)
    seed_all(session, get_settings().seed_dir, HashingEmbedder())
    assert _counts(session) == before


def test_seed_loads_paywise_brand(session: Session) -> None:
    workspace = session.get_one(Workspace, WORKSPACE_ID)
    assert workspace.voice_profile["traits"]["warm"] == 0.75
    rule_codes = set(session.scalars(select(Rule.code)))
    assert {
        "CLM-01",
        "CLM-04",
        "CLM-06",
        "CLM-08",
        "TRM-02",
        "TRM-05",
        "TON-01",
        "TON-03",
        "DSC-01",
        "DSC-02",
        "CHN-01",
        "CHN-02",
        "CHN-03",
        "RDB-01",
    } <= rule_codes
    assert session.scalar(select(func.count()).select_from(Fact)) >= 23


def test_every_fact_has_an_embedding(session: Session) -> None:
    missing = session.scalars(select(Fact.id).where(Fact.embedding.is_(None))).all()
    assert missing == []


def test_superseded_settlement_fact_is_not_current(session: Session) -> None:
    today = date(2026, 10, 22)
    old = get_fact(session, WORKSPACE_ID, "F-086")
    new = get_fact(session, WORKSPACE_ID, "F-087")
    assert old is not None and new is not None
    assert old.superseded_by == "F-087"
    assert not old.is_current(today)
    assert new.is_current(today)


def test_clm04_cites_brand_book_page_14(session: Session) -> None:
    rule = session.scalars(select(Rule).where(Rule.code == "CLM-04")).one()
    assert rule.severity.value == "critical"
    assert rule.source_ref == "brand_book.pdf#p14"
