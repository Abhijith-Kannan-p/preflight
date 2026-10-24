import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import public
from app.models import Submission, Workspace
from app.seed import WORKSPACE_ID
from app.services import history, runner, webhooks
from app.services.ratelimit import RateLimiter

Headers = dict[str, str]


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    connection = session.connection()

    def factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    monkeypatch.setattr(runner, "session_factory", factory)
    monkeypatch.setattr(history, "SessionLocal", factory)

    def run_and_wait(revision_id: str) -> None:
        worker = threading.Thread(target=runner.run_revision, args=(revision_id,))
        worker.start()
        worker.join()

    monkeypatch.setattr(runner, "start_review", run_and_wait)
    monkeypatch.setattr(webhooks, "dispatch_approval", lambda _id: None)
    yield client


def login(client: TestClient, user_id: str) -> Headers:
    token = client.post("/api/auth/demo-login", json={"user_id": user_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --- rulebook editing ------------------------------------------------------------------


def test_only_brand_managers_edit_the_rulebook(api: TestClient) -> None:
    body = {
        "code": "CLM-09",
        "category": "claims",
        "title": "No rankings",
        "description": "x" * 10,
        "severity": "major",
        "source_doc": "brand_book.pdf",
        "source_page": 20,
    }
    assert (
        api.post("/api/rulebook/rules", json=body, headers=login(api, "usr_abhi1")).status_code
        == 403
    )
    created = api.post("/api/rulebook/rules", json=body, headers=login(api, "usr_abhi3"))
    assert created.status_code == 201
    assert created.json()["version"] == 1


def test_rule_edits_create_versions_and_bump_rulebook(api: TestClient, session: Session) -> None:
    before = session.get_one(Workspace, WORKSPACE_ID).rulebook_version
    abhi3 = login(api, "usr_abhi3")
    rule = next(r for r in api.get("/api/rulebook/rules").json() if r["code"] == "TRM-02")
    update = {k: rule[k] for k in ("title", "description", "config", "source_doc", "source_page")}
    response = api.put(
        "/api/rulebook/rules/TRM-02", json={**update, "severity": "major"}, headers=abhi3
    )
    assert response.json()["version"] == 2
    versions = api.get("/api/rulebook/rules/TRM-02/versions").json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "active"), (1, "retired")]
    session.expire_all()
    assert session.get_one(Workspace, WORKSPACE_ID).rulebook_version == before + 1


def test_superseding_a_fact_makes_old_claims_outdated(api: TestClient) -> None:
    abhi3 = login(api, "usr_abhi3")
    response = api.post(
        "/api/rulebook/facts/F-087/supersede",
        json={
            "new_id": "F-088",
            "statement": "PayWise settles merchant payments in under 8 seconds.",
            "source_doc": "ops_sla_2027.pdf",
            "source_page": 2,
            "valid_from": "2026-10-01",
        },
        headers=abhi3,
    )
    assert response.status_code == 201
    facts = {f["id"]: f for f in api.get("/api/rulebook/facts").json()}
    assert facts["F-087"]["superseded_by"] == "F-088"
    assert facts["F-087"]["valid_until"] == "2026-09-30"
    review = api.post(
        "/api/reviews",
        data={
            "channel": "linkedin",
            "content": "PayWise settles merchant payments in under 10 seconds.",
        },
        headers=login(api, "usr_abhi1"),
    ).json()
    detail = api.get(f"/api/reviews/{review['id']}", headers=abhi3).json()
    assert any(
        c["verdict"] == "outdated" and c["current_fact_id"] == "F-088" for c in detail["claims"]
    )


def test_csv_export_and_import_round_trip(api: TestClient) -> None:
    abhi3 = login(api, "usr_abhi3")
    exported = api.get("/api/rulebook/export/terms.csv")
    assert exported.headers["content-type"].startswith("text/csv")
    unchanged = api.post(
        "/api/rulebook/import/terms",
        headers=abhi3,
        files={"file": ("terms.csv", exported.content, "text/csv")},
    ).json()
    assert unchanged["created"] == 0 and unchanged["errors"] == []
    added = exported.content + b'"PayWise Gold",product_name,,,true,TRM-02,Premium tier\nbad,row\n'
    result = api.post(
        "/api/rulebook/import/terms",
        headers=abhi3,
        files={"file": ("terms.csv", added, "text/csv")},
    ).json()
    assert result["created"] == 1
    assert len(result["errors"]) == 1


# --- public API, keys and rate limits --------------------------------------------------


def test_public_api_requires_a_valid_key(api: TestClient) -> None:
    admin = login(api, "usr_abhi5")
    assert (
        api.post(
            "/api/settings/keys", json={"name": "CMS"}, headers=login(api, "usr_abhi1")
        ).status_code
        == 403
    )
    created = api.post("/api/settings/keys", json={"name": "CMS"}, headers=admin).json()
    assert created["key"].startswith("pf_live_")
    body = {
        "content": "Say hello to India's #1 and 100% secure payments app!",
        "channel": "linkedin",
    }
    assert (
        api.post("/api/v1/preflight", json=body, headers={"X-API-Key": "nope"}).status_code == 401
    )
    ok = api.post("/api/v1/preflight", json=body, headers={"X-API-Key": created["key"]})
    assert ok.status_code == 200
    assert ok.json()["blocking"] is True
    assert "CLM-04" in {f["rule"]["id"] for f in ok.json()["findings"]}
    api.delete(f"/api/settings/keys/{created['id']}", headers=admin)
    assert (
        api.post("/api/v1/preflight", json=body, headers={"X-API-Key": created["key"]}).status_code
        == 401
    )


def test_public_api_is_rate_limited(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(public, "limiter", RateLimiter(limit=1, window_seconds=60))
    key = api.post(
        "/api/settings/keys", json={"name": "Rate test"}, headers=login(api, "usr_abhi5")
    ).json()["key"]
    body = {"content": "PayWise is regulated by the Reserve Bank of India.", "channel": "blog"}
    assert api.post("/api/v1/preflight", json=body, headers={"X-API-Key": key}).status_code == 200
    limited = api.post("/api/v1/preflight", json=body, headers={"X-API-Key": key})
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


# --- webhooks --------------------------------------------------------------------------


def test_webhook_signature_and_slack_test_event(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert webhooks.verify("secret", b"{}", webhooks.sign("secret", b"{}"))
    assert not webhooks.verify("secret", b"{}", webhooks.sign("other", b"{}"))
    sent: list[dict[str, Any]] = []

    def fake_post(
        url: str, content: bytes, headers: dict[str, str], timeout: float
    ) -> httpx.Response:
        sent.append({"url": url, "body": content, "headers": headers})
        return httpx.Response(200)

    monkeypatch.setattr(webhooks.httpx, "post", fake_post)
    admin = login(api, "usr_abhi5")
    hook = api.post(
        "/api/settings/webhooks",
        json={"url": "https://hooks.example.com/x", "slack_format": True},
        headers=admin,
    ).json()
    delivery = api.post(f"/api/settings/webhooks/{hook['id']}/test", headers=admin).json()
    assert delivery["ok"] is True and delivery["status_code"] == 200
    assert b'"text"' in sent[0]["body"]  # Slack format
    assert webhooks.verify(
        hook["secret"], sent[0]["body"], sent[0]["headers"]["X-Preflight-Signature"]
    )
    listed = api.get("/api/settings/webhooks", headers=admin).json()
    assert listed[0]["deliveries"][0]["ok"] is True


# --- insights, history and reset -------------------------------------------------------


def test_demo_history_feeds_insights(api: TestClient, session: Session) -> None:
    history.ensure_demo_history()
    session.expire_all()
    assert (session.scalar(select(func.count()).select_from(Submission)) or 0) >= 8
    assert api.get("/api/insights", headers=login(api, "usr_abhi1")).status_code == 403
    data = api.get("/api/insights", headers=login(api, "usr_abhi4")).json()
    assert data["totals"]["reviews"] >= 8
    assert data["totals"]["approved"] >= 4
    assert data["top_rules"] and data["by_type"] and data["trend"]
    assert any(d["disputed"] > 0 for d in data["dispute_rates"])


def test_reset_restores_a_clean_demo(
    api: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.settings.get_settings",
        lambda: type(
            "S",
            (),
            {
                "bootstrap_demo": False,
                "seed_dir": __import__("app.config").config.get_settings().seed_dir,
            },
        )(),
    )
    api.post(
        "/api/reviews",
        data={"channel": "linkedin", "content": "PayWise is great."},
        headers=login(api, "usr_abhi1"),
    )
    assert api.post("/api/settings/reset-demo", headers=login(api, "usr_abhi1")).status_code == 403
    assert api.post("/api/settings/reset-demo", headers=login(api, "usr_abhi5")).status_code == 204
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Submission)) == 0
    assert api.get("/api/audit/verify").json()["intact"] is True
