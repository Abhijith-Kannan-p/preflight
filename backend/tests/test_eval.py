from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.eval.metrics import compute
from app.eval.run import EVAL_DATE, evaluate, load_items, save
from app.models import EvalRun
from tests.engine_helpers import context


def test_metrics_per_label_and_problem_recall() -> None:
    pairs = [
        ("supported", "supported"),
        ("supported", "needs_review"),
        ("outdated", "outdated"),
        ("contradicted", "unsupported"),
        ("unsupported", "unsupported"),
        ("needs_review", "not_detected"),
    ]
    metrics, confusion = compute(pairs)
    assert confusion["contradicted"]["unsupported"] == 1
    assert metrics.per_label["unsupported"].precision == 0.5
    assert metrics.per_label["supported"].recall == 0.5
    assert metrics.problem_recall == 0.75  # 3 of 4 problem claims flagged
    assert metrics.detection_rate == round(5 / 6, 3)


def test_labelled_set_covers_all_verdicts() -> None:
    items = load_items(get_settings().data_dir / "eval" / "claims.jsonl")
    assert len(items) >= 150
    assert {i["expected"] for i in items} == {
        "supported",
        "outdated",
        "contradicted",
        "unsupported",
        "needs_review",
    }
    assert len({i["id"] for i in items}) == len(items)


def test_eval_run_is_recorded(session: Session) -> None:
    items = load_items(get_settings().data_dir / "eval" / "claims.jsonl")[:5]
    result = evaluate(items, context(session, "blog"), nli=None, embedder=None)
    assert result["config"]["eval_date"] == EVAL_DATE.isoformat()
    run = save(session, result)
    stored = session.scalars(select(EvalRun).where(EvalRun.id == run.id)).one()
    assert stored.n_items == 5
