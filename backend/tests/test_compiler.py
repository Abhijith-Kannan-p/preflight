"""Rulebook Compiler: brand book in, reviewed rules out."""

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compiler import pipeline
from app.compiler.extract import deterministic, read_pdf
from app.compiler.schema import Candidate, validate
from app.config import get_settings
from app.models import AuditEvent, Rule, RuleStatus

Headers = dict[str, str]
SAMPLE = get_settings().data_dir / "samples" / "paywise_brand_book.pdf"


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    connection = session.connection()
    monkeypatch.setattr(
        pipeline,
        "session_factory",
        lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )

    def run_and_wait(job_id: str, data: bytes, filename: str) -> None:
        worker = threading.Thread(target=pipeline.run, args=(job_id, data, filename))
        worker.start()
        worker.join()

    monkeypatch.setattr(pipeline, "start", run_and_wait)
    yield client


def login(client: TestClient, user_id: str) -> Headers:
    token = client.post("/api/auth/demo-login", json={"user_id": user_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def compile_sample(api: TestClient, who: Headers) -> dict[str, Any]:
    created = api.post("/api/compiler/jobs", data={"use_sample": "true"}, headers=who)
    assert created.status_code == 201, created.text
    job = api.get(f"/api/compiler/jobs/{created.json()['id']}", headers=who).json()
    assert job["status"] == "ready", job
    return dict(job)


def find(job: dict[str, Any], key: str) -> dict[str, Any]:
    return next(c for c in job["candidates"] if c["key"] == key)


def test_structured_extraction_reads_tables_lists_and_limits() -> None:
    pages = read_pdf(SAMPLE.read_bytes())
    keys = {c.key for c in deterministic(pages)}
    for expected in (
        "word:revolutionary",
        "pattern:CLM-01:industry-leading",
        "pattern:CLM-04:unhackable",
        "pattern:CLM-06:risk-free",
        "colour:#13294B",
        "channel:linkedin",
        "threshold:TON-03:max_exclamations_per_100_words",
        "voice",
    ):
        assert expected in keys, expected
    disclaimers = [c for c in deterministic(pages) if c.kind == "disclaimer"]
    assert any("interest-free" in c.payload["triggers"] for c in disclaimers)


def test_merge_keeps_structured_values_and_unions_triggers() -> None:
    base = {"title": "Fees", "triggers": ["fee"], "disclaimer": "Fees may apply."}
    structured = Candidate(
        kind="disclaimer", payload=validate("disclaimer", base) or {}, source_page=20, excerpt=""
    )
    from_llm = Candidate(
        kind="disclaimer",
        payload=validate("disclaimer", {**base, "triggers": ["fee", "charges"]}) or {},
        source_page=20,
        excerpt="",
        origin="llm",
    )
    merged = pipeline.merge([structured], [from_llm])
    assert len(merged) == 1
    assert merged[0].origin == "deterministic"
    assert merged[0].payload["triggers"] == ["fee", "charges"]


def test_schema_rejects_what_the_engine_cannot_run() -> None:
    assert validate("pattern", {"rule": "CLM-99", "pattern": "best"}) is None
    assert validate("colour", {"name": "Teal", "hex": "teal"}) is None
    assert validate("nonsense", {}) is None
    assert validate("colour", {"name": "Teal", "hex": "#0f766e"}) == {
        "name": "Teal",
        "hex": "#0F766E",
    }


def test_compile_runs_without_an_llm_and_says_so(api: TestClient) -> None:
    lead = login(api, "usr_abhi3")
    job = compile_sample(api, lead)
    assert job["report"]["llm"]["llm"] == "not configured"
    assert job["report"]["structured"] >= 30
    statuses = {c["match_status"] for c in job["candidates"]}
    assert {"new", "update", "duplicate"} <= statuses
    assert find(job, "word:revolutionary")["match_status"] == "new"
    assert find(job, "pattern:CLM-04:unhackable")["match_status"] == "duplicate"
    assert find(job, "pattern:CLM-01:industry-leading")["match_status"] == "update"


def test_accepting_a_candidate_activates_a_cited_rule_version(
    api: TestClient, session: Session
) -> None:
    lead = login(api, "usr_abhi3")
    job = compile_sample(api, lead)
    candidate = find(job, "pattern:CLM-01:industry-leading")
    before = session.scalars(
        select(Rule).where(Rule.code == "CLM-01", Rule.status == RuleStatus.active)
    ).one()
    decided = api.post(
        f"/api/compiler/candidates/{candidate['id']}/decision",
        json={"action": "accept"},
        headers=lead,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"] == "accepted"
    session.expire_all()
    after = session.scalars(
        select(Rule).where(Rule.code == "CLM-01", Rule.status == RuleStatus.active)
    ).one()
    assert after.version == before.version + 1
    assert after.source_page == candidate["source_page"]
    assert "industry-leading" in str(after.config)
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "compiled_rule_accepted")
    ).all()
    assert events
    # Deciding again is a no-op.
    again = api.post(
        f"/api/compiler/candidates/{candidate['id']}/decision",
        json={"action": "reject"},
        headers=lead,
    )
    assert again.json()["decision"] == "accepted"
    summary = api.get(f"/api/compiler/jobs/{job['id']}", headers=lead).json()["summary"]
    assert summary["accepted_without_edits"] == 1


def test_edits_are_validated_and_counted_as_edits(api: TestClient) -> None:
    lead = login(api, "usr_abhi3")
    job = compile_sample(api, lead)
    candidate = find(job, "word:revolutionary")
    url = f"/api/compiler/candidates/{candidate['id']}/decision"
    bad = api.post(
        url, json={"action": "accept", "payload": {"term": "", "status": "x"}}, headers=lead
    )
    assert bad.status_code == 422
    edited = {**candidate["payload"], "replacement": "brand new"}
    ok = api.post(url, json={"action": "accept", "payload": edited}, headers=lead)
    assert ok.json()["decision"] == "edited"


def test_only_rulebook_editors_compile(api: TestClient) -> None:
    writer = login(api, "usr_abhi1")
    denied = api.post("/api/compiler/jobs", data={"use_sample": "true"}, headers=writer)
    assert denied.status_code == 403
    assert (
        api.post("/api/compiler/jobs", data={}, headers=login(api, "usr_abhi3")).status_code == 422
    )
