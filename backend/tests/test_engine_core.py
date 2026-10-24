import asyncio

import pytest
from sqlalchemy.orm import Session

from app.engine.checkers.base import make_finding
from app.engine.drift import compute_drift, drift_label, revised_sentence
from app.engine.merge import merge_findings
from app.engine.normalise import from_text
from app.engine.pipeline import deterministic_checkers, run_review
from app.engine.schema import Evidence, Finding, FindingType
from app.engine.score import brand_score
from app.engine.validate import FindingRejected, check_finding
from tests.engine_helpers import LINKEDIN_SAMPLE, context
from tests.fakes import HashingEmbedder


def _finding(
    session: Session,
    rule: str,
    start: int,
    end: int,
    conf: float = 0.9,
    type: FindingType = "terminology",
) -> Finding:
    ctx = context(session)
    text = "x" * 100
    return make_finding(
        ctx.rules[rule],
        type=type,
        block=0,
        start=start,
        end=end,
        text=text[start:end],
        explanation="e",
        confidence=conf,
    )


def test_score_formula_and_breakdown(session: Session) -> None:
    findings = [
        _finding(session, "CLM-04", 0, 5),
        _finding(session, "CLM-06", 10, 15),
        _finding(session, "TRM-02", 20, 25),
        _finding(session, "TRM-02", 30, 35),
    ]
    result = brand_score(findings)
    assert result.score == 100 - 25 - 10 - 3 - 3
    assert result.breakdown[0].rule_id == "CLM-04"


def test_score_ignores_resolved_and_low_confidence(session: Session) -> None:
    resolved = _finding(session, "CLM-04", 0, 5)
    resolved.status = "accepted"
    unsure = _finding(session, "CLM-04", 10, 15)
    unsure.needs_review = True
    assert brand_score([resolved, unsure]).score == 100


def test_score_never_below_zero(session: Session) -> None:
    findings = [_finding(session, "CLM-04", i * 3, i * 3 + 2) for i in range(6)]
    assert brand_score(findings).score == 0


def test_merge_keeps_highest_and_links_duplicates(session: Session) -> None:
    a = _finding(session, "TRM-02", 0, 10, conf=0.97)
    b = _finding(session, "TRM-02", 5, 12, conf=0.8)
    c = _finding(session, "CLM-04", 5, 12, type="unsupported_claim")
    merged = merge_findings([b, a, c])
    assert [f.id for f in merged] == [c.id, a.id]
    assert a.related == [b.id]


def test_merge_routes_low_confidence_to_needs_review(session: Session) -> None:
    merged = merge_findings([_finding(session, "TRM-02", 0, 5, conf=0.5)])
    assert merged[0].needs_review


def test_validator_rejects_fabricated_ids(session: Session) -> None:
    ctx = context(session)
    doc = from_text("x" * 100)
    good = _finding(session, "TRM-02", 0, 5)
    check_finding(good, doc, ctx)

    fake_rule = good.model_copy(deep=True)
    fake_rule.rule.id = "CLM-99"
    with pytest.raises(FindingRejected, match="unknown rule"):
        check_finding(fake_rule, doc, ctx)

    fake_fact = good.model_copy(deep=True)
    fake_fact.evidence = [Evidence(fact_id="F-999", quote="made up")]
    with pytest.raises(FindingRejected, match="unknown fact"):
        check_finding(fake_fact, doc, ctx)

    wrong_span = good.model_copy(deep=True)
    wrong_span.text = "yyyyy"
    with pytest.raises(FindingRejected, match="does not match"):
        check_finding(wrong_span, doc, ctx)


def test_drift_labels_and_lexical_fallback() -> None:
    assert drift_label(0.1) == "low"
    assert drift_label(0.2) == "medium"
    assert drift_label(0.5) == "high"
    assert compute_drift("same", "same", None) == 0.0
    small = compute_drift("Paywise settles fast.", "PayWise settles fast.", None)
    big = compute_drift("Paywise settles fast.", "Totally different words here.", None)
    assert small < big


def test_revised_sentence_replaces_only_the_span(session: Session) -> None:
    doc = from_text(LINKEDIN_SAMPLE)
    start = LINKEDIN_SAMPLE.index("Paywise")
    finding = make_finding(
        context(session).rules["TRM-02"],
        type="terminology",
        block=0,
        start=start,
        end=start + 7,
        text="Paywise",
        explanation="e",
        confidence=0.97,
    )
    original, revised = revised_sentence(doc, finding, "PayWise")
    assert original == "Paywise now settles in under 5 seconds for every merchant."
    assert revised == "PayWise now settles in under 5 seconds for every merchant."


def test_pipeline_on_linkedin_sample(session: Session) -> None:
    ctx = context(session)
    events: list[str] = []

    async def emit(event: str, _data: dict[str, object]) -> None:
        events.append(event)

    result = asyncio.run(
        run_review(
            from_text(LINKEDIN_SAMPLE), ctx, deterministic_checkers(), HashingEmbedder(), emit
        )
    )
    rules = {f.rule.id for f in result.findings}
    assert {"TRM-02", "TON-03"} <= rules
    assert not result.degraded
    assert all(f.suggestion is None or f.suggestion.drift is not None for f in result.findings)
    assert events.count("checker_done") == len(deterministic_checkers())
    assert result.score.score < 100


def test_pipeline_reports_degraded_checker(session: Session) -> None:
    class Broken:
        name, label = "broken", "Broken"

        async def run(self, *_args: object) -> list[Finding]:
            raise RuntimeError("boom")

    result = asyncio.run(run_review(from_text("Hello."), context(session), [Broken()]))
    assert result.degraded
    assert result.checkers[0].error == "RuntimeError"
