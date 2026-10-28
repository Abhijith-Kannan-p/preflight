"""Doing the same thing twice never applies it twice."""

import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Decision, IdempotencyKey, Submission
from app.services import runner

Headers = dict[str, str]


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


def submissions(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Submission)) or 0


def test_running_a_review_twice_with_one_key_creates_one_review(
    api: TestClient, session: Session
) -> None:
    riya = login(api, "usr_abhi1")
    before = submissions(session)
    form = {"channel": "linkedin", "sample_id": "sample_clean"}
    headers = {**riya, "Idempotency-Key": "run-preflight-1"}
    first = api.post("/api/reviews", data=form, headers=headers)
    second = api.post("/api/reviews", data=form, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotent-Replayed"] == "true"
    assert submissions(session) == before + 1


def test_a_key_cannot_be_reused_for_a_different_request(api: TestClient) -> None:
    riya = {**login(api, "usr_abhi1"), "Idempotency-Key": "reused-key"}
    api.post(
        "/api/reviews", data={"channel": "linkedin", "sample_id": "sample_clean"}, headers=riya
    )
    other = api.post("/api/notifications/read", headers=riya)
    assert other.status_code == 422
    assert "different request" in other.json()["detail"]


def test_a_request_still_in_flight_is_not_run_again(api: TestClient, session: Session) -> None:
    riya = login(api, "usr_abhi1")
    session.add(
        IdempotencyKey(scope="usr_abhi1", key="in-flight", method="POST", path="/api/reviews")
    )
    session.commit()
    response = api.post(
        "/api/reviews",
        data={"channel": "linkedin", "sample_id": "sample_clean"},
        headers={**riya, "Idempotency-Key": "in-flight"},
    )
    assert response.status_code == 409
    assert "already being processed" in response.json()["detail"]


def test_accepting_twice_records_one_decision(api: TestClient, session: Session) -> None:
    riya = login(api, "usr_abhi1")
    created = api.post(
        "/api/reviews", data={"channel": "linkedin", "sample_id": "sample_linkedin"}, headers=riya
    ).json()
    review = api.get(f"/api/reviews/{created['id']}", headers=riya).json()
    finding = next(f for f in review["findings"] if f["suggestion"] and not f["needs_review"])
    url = f"/api/findings/{finding['id']}/decisions"
    first = api.post(url, json={"kind": "accept"}, headers=riya)
    second = api.post(url, json={"kind": "accept"}, headers=riya)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    count = select(func.count()).select_from(Decision).where(Decision.finding_id == finding["id"])
    assert session.scalar(count) == 1


def test_approving_twice_with_one_key_replays_the_first_answer(api: TestClient) -> None:
    riya, neha = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    created = api.post(
        "/api/reviews", data={"channel": "linkedin", "sample_id": "sample_clean"}, headers=riya
    ).json()
    url = f"/api/reviews/{created['id']}/transition"
    api.post(url, json={"action": "submit"}, headers=riya)
    keyed = {**neha, "Idempotency-Key": f"approve-{created['id']}"}
    first = api.post(url, json={"action": "approve"}, headers=keyed)
    second = api.post(url, json={"action": "approve"}, headers=keyed)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    # Without a key the state machine still refuses a second approval, politely.
    third = api.post(url, json={"action": "approve"}, headers=neha)
    assert third.status_code == 409


def test_a_refused_request_can_be_corrected_and_retried_with_the_same_key(
    api: TestClient,
) -> None:
    riya, neha = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    created = api.post(
        "/api/reviews",
        data={"channel": "email", "sample_id": "sample_newsletter"},
        headers=riya,
    ).json()
    review = api.get(f"/api/reviews/{created['id']}", headers=riya).json()
    criticals = [
        f for f in review["findings"] if f["severity"] == "critical" and not f["needs_review"]
    ]
    for f in criticals:
        api.post(
            f"/api/findings/{f['id']}/decisions",
            json={"kind": "dispute", "reason": "Legal cleared this copy."},
            headers=riya,
        )
    url = f"/api/reviews/{created['id']}/transition"
    api.post(url, json={"action": "submit"}, headers=riya)
    keyed = {**neha, "Idempotency-Key": "approve-newsletter"}
    refused = api.post(url, json={"action": "approve"}, headers=keyed)
    assert refused.status_code == 409
    overrides = [
        {"finding_id": f["id"], "reason": "Legal approved it in writing."} for f in criticals
    ]
    fixed = api.post(url, json={"action": "approve", "overrides": overrides}, headers=keyed)
    assert fixed.status_code == 200
