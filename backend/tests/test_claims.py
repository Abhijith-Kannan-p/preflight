import asyncio
from collections.abc import Sequence

import pytest
from sqlalchemy.orm import Session

from app.engine.claims.detect import detect_claims
from app.engine.claims.ledger import ClaimLedger
from app.engine.claims.quantities import compare, extract
from app.engine.claims.quote import best_quote, quote_is_verbatim
from app.engine.normalise import from_text
from app.engine.schema import Finding
from app.ml.nli import NliScores
from tests.engine_helpers import LINKEDIN_SAMPLE, context


class TableNli:
    """Fake NLI: entailment for listed (fact, claim) pairs, neutral for everything else."""

    name = "table-nli"

    def __init__(self, entailed: set[tuple[str, str]] | None = None) -> None:
        self.entailed = entailed or set()

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]:
        return [
            {"entailment": 0.95, "contradiction": 0.01, "neutral": 0.04}
            if pair in self.entailed
            else {"entailment": 0.05, "contradiction": 0.05, "neutral": 0.9}
            for pair in pairs
        ]


def _run(
    session: Session, text: str, nli: TableNli | None = None, channel: str = "linkedin"
) -> tuple[ClaimLedger, list[Finding]]:
    ledger = ClaimLedger(nli or TableNli(), embedder=None)
    findings = asyncio.run(ledger.run(from_text(text), context(session, channel)))
    return ledger, findings


# --- Quantities ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("settles in under 5 seconds", [("time", 5.0)]),
        ("in under 10 minutes", [("time", 600.0)]),
        ("over 12 million registered users", [("count:user", 12e6)]),
        ("a 1.5% merchant fee", [("fee", 1.5)]),
        ("you pay zero fees on cards", [("fee", 0.0)]),
        ("rated 4.6 out of 5", [("rating", 4.6)]),
        ("AES-256 encryption and a new milestone", []),
        ("founded in 2019", []),
        ("India's #1 app", []),
    ],
)
def test_quantity_extraction(text: str, expected: list[tuple[str, float]]) -> None:
    assert [(q.family, q.value) for q in extract(text)] == expected


def test_numeric_compare() -> None:
    assert compare("under 5 seconds", "in under 10 seconds.")[0] == "mismatch"
    assert compare("under 10 seconds", "in under 10 seconds.")[0] == "match"
    assert compare("12 Indian languages", "settles in under 10 seconds.")[0] == "na"
    assert compare("ten bill payments", "up to 30 interest-free days.")[0] == "na"


# --- Quote check -----------------------------------------------------------------------


def test_quote_is_verbatim_span_of_fact() -> None:
    fact = "PayWise secures payments with bank-grade AES-256 encryption and is PCI DSS certified."
    quote = best_quote("Every payment is protected with bank-grade AES-256 encryption.", fact)
    assert quote == "with bank-grade AES-256 encryption"
    assert quote_is_verbatim(quote, fact)
    assert best_quote("A completely different sentence.", fact) is None


# --- Detection -------------------------------------------------------------------------


def test_detects_every_claim_in_linkedin_sample(session: Session) -> None:
    claims = detect_claims(from_text(LINKEDIN_SAMPLE), context(session))
    hits = {h.rule_code: h.span.text for c in claims for h in c.hits}
    assert hits == {"CLM-01": "India's #1", "CLM-04": "100% secure", "CLM-06": "never worry again"}
    assert any("under 5 seconds" in c.span.text for c in claims)


def test_splits_compound_and_relative_clauses(session: Session) -> None:
    text = (
        "PayWise, which is regulated by the Reserve Bank of India, serves over 12 million "
        "registered users. PayWise Business serves over 2 million merchants, and UPI payments "
        "on PayWise have zero merchant discount rate."
    )
    hypotheses = [c.hypothesis for c in detect_claims(from_text(text), context(session))]
    assert "PayWise is regulated by the Reserve Bank of India" in hypotheses
    assert "PayWise serves over 12 million registered users." in hypotheses
    assert "UPI payments on PayWise have zero merchant discount rate." in hypotheses


def test_greetings_and_datelines_are_not_claims(session: Session) -> None:
    text = "Hi there,\n\nBengaluru, 20 October 2026.\n\nWarm regards,\nThe PayWise team"
    assert detect_claims(from_text(text), context(session)) == []


# --- Verdicts --------------------------------------------------------------------------


def test_linkedin_sample_reproduces_round1_scenario(session: Session) -> None:
    ledger, findings = _run(session, LINKEDIN_SAMPLE)
    by_rule = {f.rule.id: f for f in findings}
    assert by_rule["CLM-04"].severity == "critical"
    assert by_rule["CLM-04"].rule.source == "brand_book.pdf#p14"
    assert by_rule["CLM-01"].severity == "critical"
    assert by_rule["CLM-06"].severity == "major"
    outdated = by_rule["CLM-03"]
    assert outdated.type == "outdated_fact"
    assert outdated.text == "under 5 seconds"
    assert outdated.suggestion and outdated.suggestion.text == "under 10 seconds"
    assert {e.fact_id for e in outdated.evidence} == {"F-086", "F-087"}
    verdicts = {r.verdict for r in ledger.records}
    assert "outdated" in verdicts


def test_numeric_mismatch_is_contradiction_regardless_of_nli(session: Session) -> None:
    _, findings = _run(session, "With PayWise you pay zero fees on all PayWise Card payments.")
    contradicted = [f for f in findings if f.rule.id == "CLM-02"]
    assert len(contradicted) == 1
    assert contradicted[0].evidence[0].fact_id == "F-046"
    assert contradicted[0].suggestion and contradicted[0].suggestion.text == "a 1.5% fee"


def test_entailed_claim_with_quote_is_supported(session: Session) -> None:
    fact = "PayWise is regulated as a payment aggregator by the Reserve Bank of India."
    claim = "PayWise is regulated as a payment aggregator by the Reserve Bank of India."
    ledger, findings = _run(session, claim, TableNli({(fact, claim)}))
    record = ledger.records[0]
    assert record.verdict == "supported"
    assert record.fact_id == "F-210"
    assert record.quote and quote_is_verbatim(record.quote, fact)
    assert findings == []
    assert any("Quote check passed" in step for step in record.steps)


def test_matching_numbers_support_claim_when_nli_is_inconclusive(session: Session) -> None:
    ledger, findings = _run(session, "PayWise settles merchant payments in under 10 seconds.")
    assert ledger.records[0].verdict == "supported"
    assert ledger.records[0].confidence == 0.75
    assert findings == []


def test_unknown_number_is_unsupported(session: Session) -> None:
    ledger, findings = _run(session, "PayWise has won 7 national awards.")
    assert ledger.records[0].verdict == "unsupported"
    assert [f.rule.id for f in findings] == ["CLM-05"]


def test_free_needs_disclaimer_or_fact(session: Session) -> None:
    _, without = _run(session, "PayWise Business includes free setup.")
    assert "CLM-08" in {f.rule.id for f in without}
    _, with_disclaimer = _run(session, "PayWise Business includes free setup. T&C apply.")
    assert "CLM-08" not in {f.rule.id for f in with_disclaimer}


def test_lexical_fallback_without_nli_model(session: Session) -> None:
    ledger = ClaimLedger(nli=None, embedder=None)
    asyncio.run(ledger.run(from_text(LINKEDIN_SAMPLE), context(session)))
    assert any(r.verdict == "outdated" for r in ledger.records)
    assert any("lexical fallback" in s for r in ledger.records for s in r.steps)
