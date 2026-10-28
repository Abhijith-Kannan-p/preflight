"""Governance intelligence: Stale-Content Radar, Guideline Health and the Creator Coach."""

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.health import group_reasons
from app.models import Notification
from app.services import runner

Headers = dict[str, str]
SETTLEMENT = "PayWise settles merchant payments in under 10 seconds."


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    connection = session.connection()
    monkeypatch.setattr(
        runner,
        "session_factory",
        lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )

    def run_and_wait(revision_id: str) -> None:
        worker = threading.Thread(target=runner.run_revision, args=(revision_id,))
        worker.start()
        worker.join()

    monkeypatch.setattr(runner, "start_review", run_and_wait)
    yield client


def login(client: TestClient, user_id: str) -> Headers:
    token = client.post("/api/auth/demo-login", json={"user_id": user_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def review(api: TestClient, who: Headers, content: str, title: str) -> dict[str, Any]:
    created = api.post(
        "/api/reviews",
        data={"channel": "linkedin", "content": content, "title": title},
        headers=who,
    )
    assert created.status_code == 201, created.text
    return dict(api.get(f"/api/reviews/{created.json()['id']}", headers=who).json())


def clear(api: TestClient, review_id: str, author: Headers, approver: Headers) -> None:
    url = f"/api/reviews/{review_id}/transition"
    assert api.post(url, json={"action": "submit"}, headers=author).status_code == 200
    assert api.post(url, json={"action": "approve"}, headers=approver).status_code == 200


# --- Stale-Content Radar ----------------------------------------------------------------


def test_radar_lists_every_cleared_item_that_relied_on_a_changed_fact(
    api: TestClient, session: Session
) -> None:
    riya, neha, manager = login(api, "usr_abhi1"), login(api, "usr_abhi4"), login(api, "usr_abhi3")
    dependent = []
    for n in range(4):
        item = review(api, riya, f"{SETTLEMENT} Story {n} for our shops.", f"Settlement story {n}")
        assert "F-087" in {c["fact_id"] for c in item["claims"]}, item["claims"]
        clear(api, item["submission"]["id"], riya, neha)
        dependent.append(item["submission"]["id"])
    unrelated = review(
        api, riya, "PayWise customer support is available 24x7 in English and Hindi.", "Support"
    )
    clear(api, unrelated["submission"]["id"], riya, neha)
    draft = review(api, riya, SETTLEMENT, "Still a draft")

    assert api.get("/api/radar", headers=manager).json()["entries"] == []
    changed = api.post("/api/radar/simulate", headers=manager)
    assert changed.status_code == 201, changed.text
    assert changed.json()["affected"] == 4

    radar = api.get("/api/radar", headers=manager).json()
    listed = {e["submission_id"] for e in radar["entries"]}
    assert listed == set(dependent), "every dependent cleared item, and nothing else"
    assert draft["submission"]["id"] not in listed
    entry = radar["entries"][0]
    assert entry["fact_id"] == "F-087" and entry["change"] == "superseded"
    assert "10 seconds" in entry["old_value"] and "15 seconds" in entry["new_value"]
    assert "under 10 seconds" in entry["sentence"]

    notified = session.scalars(
        select(Notification).where(Notification.kind == "stale_content")
    ).all()
    assert {n.submission_id for n in notified} == set(dependent)

    again = api.post(f"/api/radar/{dependent[0]}/recheck", headers=riya)
    assert again.status_code == 201
    rechecked = api.get(f"/api/reviews/{again.json()['id']}", headers=riya).json()
    assert "CLM-03" in {f["rule"]["id"] for f in rechecked["findings"]}, "now outdated"


def test_editing_a_fact_flags_items_cleared_before_the_edit(api: TestClient) -> None:
    riya, neha, manager = login(api, "usr_abhi1"), login(api, "usr_abhi4"), login(api, "usr_abhi3")
    item = review(api, riya, SETTLEMENT, "Settlement")
    clear(api, item["submission"]["id"], riya, neha)
    edited = api.put(
        "/api/rulebook/facts/F-087",
        json={
            "statement": "PayWise settles merchant payments in under 12 seconds.",
            "source_doc": "ops_sla_2026.pdf",
            "source_page": 2,
            "valid_from": "2026-09-02",
            "valid_until": None,
        },
        headers=manager,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["affected"] == 1
    entry = api.get("/api/radar", headers=manager).json()["entries"][0]
    assert entry["change"] == "edited" and "12 seconds" in entry["new_value"]


# --- Guideline Health -------------------------------------------------------------------


def test_reasons_are_grouped_by_theme() -> None:
    groups = group_reasons(
        [
            "We 'offer' support here; this is not a promotion.",
            "Not a promotion: 'offer' as in provide.",
            "We 'offer' a service, not a promotional offer.",
            "Eligibility is explained on the landing page.",
        ]
    )
    assert [g["count"] for g in groups] == [3, 1]


def test_guideline_health_rates_and_versions(api: TestClient) -> None:
    riya, manager = login(api, "usr_abhi1"), login(api, "usr_abhi3")
    for n in range(4):
        item = review(api, riya, f"We offer 24x7 support, week {n}.", f"Support {n}")
        finding = next(f for f in item["findings"] if f["rule"]["id"] == "DSC-01")
        if n < 3:
            api.post(
                f"/api/findings/{finding['id']}/decisions",
                json={"kind": "dispute", "reason": "We 'offer' support; this is not a promotion."},
                headers=riya,
            )
    report = api.get("/api/governance/health", headers=manager).json()
    dsc = next(r for r in report["rules"] if r["code"] == "DSC-01")
    assert dsc["current"]["raised"] == 4 and dsc["current"]["disputed"] == 3
    assert dsc["current"]["ambiguity"] == pytest.approx(0.45)
    assert dsc["flagged"] is True
    assert dsc["reason_groups"][0]["count"] == 3
    assert "ambiguity" in report["formula"]

    suggestion = api.post("/api/governance/rules/DSC-01/suggest", headers=manager)
    assert suggestion.status_code == 200
    body = suggestion.json()
    assert body["source"] == "deterministic", "no LLM in tests: a labelled draft"
    assert "promotion" in body["description"]

    published = api.put(
        "/api/rulebook/rules/DSC-01",
        json={
            "title": "Promotional offer disclaimer",
            "description": "Promotions need T&C apply. Describing a service is not a promotion.",
            "severity": "major",
            "config": {
                "triggers": ["special offer", "cashback", "free"],
                "disclaimer": "T&C apply.",
            },
            "source_doc": "compliance_note.pdf",
            "source_page": 2,
        },
        headers=manager,
    )
    assert published.status_code == 200
    after = api.get("/api/governance/health", headers=manager).json()
    dsc = next(r for r in after["rules"] if r["code"] == "DSC-01")
    assert [v["version"] for v in dsc["versions"]] == [1, 2]
    assert dsc["versions"][0]["dispute_rate"] == pytest.approx(0.75)
    assert dsc["version"] == 2 and dsc["current"]["raised"] == 0


# --- Creator Coach ----------------------------------------------------------------------


def test_coach_finds_repeated_mistakes_and_gives_tips(api: TestClient) -> None:
    riya = login(api, "usr_abhi1")
    for n, text in enumerate(
        [
            "Paywise is the best app for shops.",
            "Paywise makes payday simple.",
            "Paywise is the best way to get paid.",
            "Pay smarter with Paywise.",
        ]
    ):
        review(api, riya, text, f"Draft {n}")
    me = api.get("/api/coach/me", headers=riya).json()
    assert me["submissions"] == 4
    assert me["recurring"][0]["rule"] == "TRM-02"
    assert me["repeat_rate"] > 0
    tip = next(t for t in me["tips"] if t["rule"] == "TRM-02")
    assert tip["approved_wording"] == 'write "PayWise"'
    assert "Paywise" in tip["your_example"]
    assert me["trend"] in {"repeating", "steady", "improving"}
    assert api.get("/api/coach", headers=riya).status_code == 403, "team view is for managers"
    assert len(api.get("/api/coach", headers=login(api, "usr_abhi3")).json()) == 2
