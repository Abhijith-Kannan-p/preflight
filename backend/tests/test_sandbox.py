"""Per-visitor sandboxes: cloning, isolation, reset, expiry and the shared review cache."""

import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.models import SANDBOX_KIND, AuditEvent, Fact, Rule, Submission, User, Workspace
from app.seed import WORKSPACE_ID
from app.services import runner, sandbox

Headers = dict[str, str]


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Reviews run synchronously against the test database."""
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


def visitor(api: TestClient, user_id: str | None = None) -> tuple[Headers, dict[str, Any]]:
    """Open (or resume, via the client's cookie jar) a sandbox session."""
    body = api.post("/api/sandbox/session", json={"user_id": user_id}).json()
    return {"Authorization": f"Bearer {body['token']}"}, body


def new_visitor(api: TestClient, user_id: str | None = None) -> tuple[Headers, dict[str, Any]]:
    api.cookies.clear()
    return visitor(api, user_id)


def review(api: TestClient, headers: Headers, sample: str = "sample_clean") -> str:
    response = api.post(
        "/api/reviews", data={"channel": "linkedin", "sample_id": sample}, headers=headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def count(session: Session, model: Any, workspace_id: str) -> int:
    query = select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
    return session.scalar(query) or 0


def test_session_creates_then_resumes_a_sandbox_from_the_cookie(api: TestClient) -> None:
    api.cookies.clear()
    first = api.post("/api/sandbox/session", json={})
    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["workspace_id"].startswith("sbx_")
    assert body["user"]["name"] == "abhi1"
    cookie = first.headers["set-cookie"]
    assert "pf_sandbox=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie

    again = api.post("/api/sandbox/session", json={"user_id": "usr_abhi4"}).json()
    assert again["created"] is False
    assert again["workspace_id"] == body["workspace_id"]
    assert again["user"]["name"] == "abhi4"
    assert again["user"]["id"] != "usr_abhi4", "sandbox personas are copies"


def test_clone_copies_brand_people_history_and_a_valid_audit_chain(
    api: TestClient, session: Session
) -> None:
    # Give the template some history so the clone has reviews and audit events to copy.
    template_user = api.post("/api/auth/demo-login", json={"user_id": "usr_abhi1"}).json()
    review(api, {"Authorization": f"Bearer {template_user['token']}"})

    started = time.perf_counter()
    ws = sandbox.create_sandbox(session)
    elapsed = time.perf_counter() - started
    assert elapsed < 3, f"cloning took {elapsed:.2f} s"

    assert ws.kind == SANDBOX_KIND
    for model in (Rule, Fact, User, Submission):
        assert count(session, model, ws.id) == count(session, model, WORKSPACE_ID) > 0
    copied = session.scalar(select(Fact).where(Fact.workspace_id == ws.id, Fact.id == "F-087"))
    assert copied is not None and copied.embedding is not None
    assert count(session, AuditEvent, ws.id) == count(session, AuditEvent, WORKSPACE_ID)
    assert audit.verify_chain(session, ws.id).intact
    assert audit.verify_chain(session, WORKSPACE_ID).intact


def test_visitors_cannot_see_or_touch_each_others_work(api: TestClient) -> None:
    alice, alice_session = new_visitor(api)
    alice_review = review(api, alice)
    bob, bob_session = new_visitor(api)
    assert alice_session["workspace_id"] != bob_session["workspace_id"]

    bob_ids = {r["id"] for r in api.get("/api/reviews", headers=bob).json()}
    assert alice_review not in bob_ids
    assert api.get(f"/api/reviews/{alice_review}", headers=bob).status_code == 404

    # A rulebook edit in one sandbox does not reach the other or the template.
    bob_brand_manager, _ = visitor(api, "usr_abhi3")
    edited = api.put(
        "/api/rulebook/rules/CLM-04",
        json={
            "title": "Edited in Bob's sandbox",
            "description": "Changed in one sandbox only.",
            "severity": "minor",
            "config": {},
            "source_doc": "brand_book.pdf",
            "source_page": 14,
        },
        headers=bob_brand_manager,
    )
    assert edited.status_code == 200, edited.text
    alice_rules = api.get("/api/rulebook/rules", headers=alice).json()
    assert {r["code"]: r["title"] for r in alice_rules}["CLM-04"] != "Edited in Bob's sandbox"
    template_rules = api.get("/api/rulebook/rules").json()
    assert {r["code"]: r["title"] for r in template_rules}["CLM-04"] != "Edited in Bob's sandbox"


def test_reset_only_touches_the_visitors_own_sandbox(api: TestClient) -> None:
    alice, alice_session = new_visitor(api)
    alice_review = review(api, alice)
    bob, bob_session = new_visitor(api)
    review(api, bob)

    reset = api.post("/api/sandbox/reset", json={"user_id": "usr_abhi5"})
    assert reset.status_code == 200
    after = reset.json()
    assert after["workspace_id"] == bob_session["workspace_id"], "the cookie stays valid"
    fresh = {"Authorization": f"Bearer {after['token']}"}
    assert api.get("/api/reviews?scope=all", headers=fresh).json() == []
    assert api.get("/api/audit/verify", headers=fresh).json()["intact"] is True

    # Alice's sandbox is untouched; Bob's old token named personas that no longer exist.
    assert api.get(f"/api/reviews/{alice_review}", headers=alice).status_code == 200
    assert api.get("/api/reviews", headers=bob).status_code == 401
    assert alice_session["workspace_id"] != after["workspace_id"]


def test_admin_reset_in_a_sandbox_is_sandbox_only(api: TestClient) -> None:
    alice, _ = new_visitor(api)
    alice_review = review(api, alice)
    bob_admin, _ = new_visitor(api, "usr_abhi5")
    assert api.post("/api/settings/reset-demo", headers=bob_admin).status_code == 200
    assert api.get(f"/api/reviews/{alice_review}", headers=alice).status_code == 200


def test_idle_sandboxes_expire_and_are_swept(api: TestClient, session: Session) -> None:
    _, body = new_visitor(api)
    stale = session.get_one(Workspace, body["workspace_id"])
    stale.last_active_at = stale.created_at - timedelta(hours=25)
    session.commit()

    resumed = api.post("/api/sandbox/session", json={}).json()
    assert resumed["created"] is True
    assert resumed["workspace_id"] != body["workspace_id"]
    session.expire_all()
    assert session.get(Workspace, body["workspace_id"]) is None

    other = session.get_one(Workspace, resumed["workspace_id"])
    other.last_active_at = other.created_at - timedelta(hours=25)
    session.commit()
    assert sandbox.sweep(session) >= 1
    session.expire_all()
    assert session.get(Workspace, resumed["workspace_id"]) is None
    assert session.get(Workspace, WORKSPACE_ID) is not None, "the template is never swept"


def test_identical_drafts_in_identical_sandboxes_reuse_one_review(api: TestClient) -> None:
    alice, _ = new_visitor(api)
    first = review(api, alice, "sample_linkedin")
    bob, _ = new_visitor(api)
    second = review(api, bob, "sample_linkedin")
    one = api.get(f"/api/reviews/{first}", headers=alice).json()
    two = api.get(f"/api/reviews/{second}", headers=bob).json()
    assert two["revision"]["report"].get("cached_from") == one["revision"]["id"]
    assert two["revision"]["brand_score"] == one["revision"]["brand_score"]


def test_a_changed_rulebook_is_not_served_from_another_sandboxs_cache(api: TestClient) -> None:
    alice, _ = new_visitor(api)
    review(api, alice, "sample_linkedin")
    bob_brand_manager, _ = new_visitor(api, "usr_abhi3")
    assert api.delete("/api/rulebook/rules/CLM-04", headers=bob_brand_manager).status_code == 204
    bob, _ = visitor(api, "usr_abhi1")
    mine = api.get(f"/api/reviews/{review(api, bob, 'sample_linkedin')}", headers=bob).json()
    assert "cached_from" not in mine["revision"]["report"]
    assert "CLM-04" not in {f["rule"]["id"] for f in mine["findings"]}
