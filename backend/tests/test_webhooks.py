"""Webhooks: retries with backoff, the delivery log, resend, and the three events."""

import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Webhook
from app.services import runner, webhooks
from tests.test_governance import clear, login, review

Sent = list[dict[str, Any]]


@pytest.fixture
def api(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    connection = session.connection()

    def factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    monkeypatch.setattr(runner, "session_factory", factory)
    monkeypatch.setattr(webhooks, "session_factory", factory)
    monkeypatch.setattr(webhooks, "_spawn", lambda target, _name: target())
    monkeypatch.setattr(webhooks, "BACKOFF_SECONDS", 0.0)

    def run_and_wait(revision_id: str) -> None:
        worker = threading.Thread(target=runner.run_revision, args=(revision_id,))
        worker.start()
        worker.join()

    monkeypatch.setattr(runner, "start_review", run_and_wait)
    yield client


def fake_endpoint(monkeypatch: pytest.MonkeyPatch, codes: list[int | None]) -> Sent:
    """Answer with these status codes in turn (None = network error), then 200."""
    sent: Sent = []

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> httpx.Response:
        sent.append({"url": url, "body": content, "headers": headers})
        code = codes.pop(0) if codes else 200
        if code is None:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(code)

    monkeypatch.setattr(webhooks.httpx, "post", post)
    return sent


def hook(session: Session, events: list[str] | None = None) -> Webhook:
    webhook = Webhook(
        workspace_id="ws_paywise",
        url="https://hooks.example.com/x",
        secret="s3cret",
        events=events or list(webhooks.EVENTS),
    )
    session.add(webhook)
    session.commit()
    return webhook


EVENT = {"event": "submission.approved", "submission": {"id": "sub_1"}}


def test_retries_with_backoff_until_delivered(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []
    monkeypatch.setattr(webhooks.time, "sleep", waits.append)
    sent = fake_endpoint(monkeypatch, [503, None, 200])
    delivery = webhooks.deliver(session, hook(session), EVENT)
    assert delivery.status == "delivered" and delivery.ok
    assert delivery.attempts == 3 and len(sent) == 3
    assert [a["status_code"] for a in delivery.attempt_log] == [503, None, 200]
    assert waits == [2.0, 4.0], "exponential backoff"


def test_client_errors_are_final_and_retries_stop_at_three(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webhooks.time, "sleep", lambda _s: None)
    fake_endpoint(monkeypatch, [404])
    webhook = hook(session)
    gone = webhooks.deliver(session, webhook, EVENT)
    assert gone.status == "failed" and gone.attempts == 1

    fake_endpoint(monkeypatch, [500, 500, 500, 500])
    down = webhooks.deliver(session, webhook, EVENT)
    assert down.status == "failed" and down.attempts == 3


def test_resend_creates_a_linked_delivery(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_endpoint(monkeypatch, [500, 500, 500])
    admin = login(api, "usr_abhi5")
    created = api.post(
        "/api/settings/webhooks", json={"url": "https://hooks.example.com/y"}, headers=admin
    ).json()
    assert created["events"] == list(webhooks.EVENTS)
    first = api.post(f"/api/settings/webhooks/{created['id']}/test", headers=admin).json()
    listed = api.get("/api/settings/webhooks", headers=admin).json()[0]["deliveries"]
    assert listed[0]["status"] == "failed" and listed[0]["attempts"] == 3

    again = api.post(
        f"/api/settings/webhooks/{created['id']}/deliveries/{first['id']}/resend", headers=admin
    ).json()
    assert again["status"] == "delivered" and again["resent_from"] == first["id"]
    assert sent[-1]["body"] == sent[0]["body"], "the same event, byte for byte"
    writer = login(api, "usr_abhi1")
    denied = api.post(
        f"/api/settings/webhooks/{created['id']}/deliveries/{first['id']}/resend", headers=writer
    )
    assert denied.status_code == 403


def test_critical_and_published_events_reach_subscribers_only(
    api: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = fake_endpoint(monkeypatch, [])
    admin = login(api, "usr_abhi5")
    url = "/api/settings/webhooks"
    critical_only = api.post(
        url,
        json={"url": "https://hooks.example.com/critical", "events": ["finding.critical"]},
        headers=admin,
    ).json()
    api.post(
        url,
        json={"url": "https://hooks.example.com/published", "events": ["review.published"]},
        headers=admin,
    )

    writer, approver = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    risky = review(api, writer, "PayWise is 100% secure and unhackable.", "Risky")
    to_critical = [s for s in sent if s["url"].endswith("/critical")]
    assert len(to_critical) == 1 and b'"finding.critical"' in to_critical[0]["body"]
    assert b"CLM-04" in to_critical[0]["body"]
    assert not any(s["url"].endswith("/published") for s in sent)

    safe = review(api, writer, "PayWise customer support is available 24x7.", "Support")
    assert len([s for s in sent if s["url"].endswith("/critical")]) == 1, "no criticals, no event"
    clear(api, safe["submission"]["id"], writer, approver)
    published = api.post(
        f"/api/reviews/{safe['submission']['id']}/transition",
        json={"action": "publish"},
        headers=approver,
    )
    assert published.status_code == 200, published.text
    to_published = [s for s in sent if s["url"].endswith("/published")]
    assert len(to_published) == 1 and b'"review.published"' in to_published[0]["body"]

    edited = api.patch(
        f"{url}/{critical_only['id']}", json={"events": ["submission.approved"]}, headers=admin
    )
    assert edited.json()["events"] == ["submission.approved"]
    assert (
        api.patch(f"{url}/{critical_only['id']}", json={"events": []}, headers=admin).status_code
        == 422
    )
    assert risky["submission"]["id"]
