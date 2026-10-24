import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import audit
from app.models import Finding, SubmissionState
from app.services import runner
from app.workflow import TransitionError, apply_suggestions, check_transition

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


def login(client: TestClient, user_id: str) -> Headers:
    token = client.post("/api/auth/demo-login", json={"user_id": user_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create(client: TestClient, headers: Headers, sample: str, channel: str) -> dict[str, Any]:
    response = client.post(
        "/api/reviews", data={"channel": channel, "sample_id": sample}, headers=headers
    )
    assert response.status_code == 201, response.text
    review: dict[str, Any] = client.get(
        f"/api/reviews/{response.json()['id']}", headers=headers
    ).json()
    return review


def by_rule(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["rule"]["id"]: f for f in review["findings"]}


# --- unit: state machine and suggestion application -----------------------------------


def test_illegal_transitions_are_rejected() -> None:
    assert check_transition(SubmissionState.draft, "submit").target == SubmissionState.in_review
    with pytest.raises(TransitionError, match="Cannot 'approve' from 'draft'"):
        check_transition(SubmissionState.draft, "approve")
    with pytest.raises(TransitionError):
        check_transition(SubmissionState.published, "submit")


def _finding(start: int, end: int, text_: str, applied: str, position: int) -> Finding:
    return Finding(
        span={"block": 0, "start": start, "end": end},
        text=text_,
        applied_text=applied,
        status="accepted",
        position=position,
    )


def test_apply_suggestions_right_to_left_and_skips_overlaps() -> None:
    block = "Paywise is 100% secure!"
    blocks, applied = apply_suggestions(
        [block],
        [
            _finding(0, 7, "Paywise", "PayWise", 0),
            _finding(11, 22, "100% secure", "bank-grade encrypted", 1),
            _finding(16, 22, "secure", "safe", 2),  # overlaps a higher-ranked edit
        ],
    )
    assert blocks == ["PayWise is bank-grade encrypted!"]
    assert applied == 2


# --- API: golden path -----------------------------------------------------------------


def test_golden_path_from_draft_to_approval(api: TestClient, session: Session) -> None:
    riya, neha = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    review = create(api, riya, "sample_linkedin", "linkedin")
    review_id = review["submission"]["id"]
    rules = by_rule(review)
    assert rules["CLM-04"]["severity"] == "critical"
    assert rules["CLM-03"]["suggestion"]["text"] == "under 10 seconds"
    assert review["gate"]["can_submit"] is False
    assert any(c["verdict"] == "outdated" for c in review["claims"])

    blocked = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "submit"}, headers=riya
    )
    assert blocked.status_code == 409
    assert rules["CLM-04"]["id"] in blocked.json()["detail"]["blocking"]

    for f in review["findings"]:
        if f["suggestion"] and not f["needs_review"]:
            r = api.post(
                f"/api/findings/{f['id']}/decisions", json={"kind": "accept"}, headers=riya
            )
            assert r.status_code == 201, r.text
    for f in review["findings"]:
        if f["status"] == "open" and not f["suggestion"]:
            api.post(
                f"/api/findings/{f['id']}/decisions",
                json={"kind": "dispute", "reason": "Tone matches campaign brief."},
                headers=riya,
            )

    draft = api.get(f"/api/reviews/{review_id}/draft", headers=riya).json()
    assert "PayWise now settles in under 10 seconds" in draft["content"]
    assert "100% secure" not in draft["content"]

    assert api.post(f"/api/reviews/{review_id}/revisions", json={}, headers=riya).status_code == 201
    second = api.get(f"/api/reviews/{review_id}", headers=riya).json()
    assert second["revision"]["number"] == 2
    assert second["revision"]["brand_score"] > review["revision"]["brand_score"]
    assert second["gate"]["can_submit"] is True

    diff = api.get(f"/api/reviews/{review_id}/diff?from=1&to=2", headers=riya).json()
    assert "CLM-04" in {f["rule"]["id"] for f in diff["resolved"]}

    submitted = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "submit"}, headers=riya
    )
    assert submitted.json()["submission"]["state"] == "in_review"

    forbidden = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "approve"}, headers=riya
    )
    assert forbidden.status_code == 403

    approved = api.post(
        f"/api/reviews/{review_id}/transition",
        json={"action": "approve", "comment": "Looks good."},
        headers=neha,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["submission"]["state"] == "approved"
    assert approved.json()["submission"]["approved_by"]["id"] == "usr_abhi4"

    again = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "approve"}, headers=neha
    )
    assert again.status_code == 409

    kinds = [n["kind"] for n in api.get("/api/notifications", headers=riya).json()]
    assert "approved" in kinds
    assert api.get("/api/audit/verify").json()["intact"] is True
    trail = api.get(f"/api/audit?entity_id={review_id}", headers=neha).json()
    assert {"created", "submit", "approve"} <= {e["action"] for e in trail}


def test_critical_override_needs_written_reason(api: TestClient) -> None:
    riya, neha = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    review = create(api, riya, "sample_newsletter", "email")
    review_id = review["submission"]["id"]
    criticals = [
        f for f in review["findings"] if f["severity"] == "critical" and not f["needs_review"]
    ]
    assert {"DSC-02", "CLM-02"} <= {f["rule"]["id"] for f in criticals}

    short = api.post(
        f"/api/findings/{criticals[0]['id']}/decisions",
        json={"kind": "dispute", "reason": "no"},
        headers=riya,
    )
    assert short.status_code == 422
    for f in criticals:
        api.post(
            f"/api/findings/{f['id']}/decisions",
            json={"kind": "dispute", "reason": "Legal cleared this copy on 20 Oct."},
            headers=riya,
        )
    submit = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "submit"}, headers=riya
    )
    assert submit.status_code == 200, "disputed criticals may go to the approver"

    gate = api.post(
        f"/api/reviews/{review_id}/transition", json={"action": "approve"}, headers=neha
    )
    assert gate.status_code == 409
    assert set(gate.json()["detail"]["blocking"]) == {f["id"] for f in criticals}

    overrides = [
        {"finding_id": f["id"], "reason": "Legal approved the wording in writing."}
        for f in criticals
    ]
    ok = api.post(
        f"/api/reviews/{review_id}/transition",
        json={"action": "approve", "overrides": overrides},
        headers=neha,
    )
    assert ok.status_code == 200
    assert sum(d["kind"] == "override" for d in ok.json()["decisions"]) == len(criticals)


def test_permissions_are_enforced_in_backend(api: TestClient) -> None:
    admin, neha = login(api, "usr_abhi5"), login(api, "usr_abhi4")
    assert (
        api.post("/api/reviews", data={"channel": "x", "content": "Hi"}, headers=neha).status_code
        == 403
    )
    riya = login(api, "usr_abhi1")
    review = create(api, riya, "sample_clean", "linkedin")
    comment = api.post(
        f"/api/reviews/{review['submission']['id']}/comments",
        json={"body": "Admin note"},
        headers=admin,
    )
    assert comment.status_code == 403
    assert api.get("/api/reviews").status_code == 401


def test_clean_post_scores_high(api: TestClient) -> None:
    review = create(api, login(api, "usr_abhi1"), "sample_clean", "linkedin")
    assert review["revision"]["brand_score"] >= 90
    assert review["gate"]["can_submit"] is True
    assert all(c["verdict"] == "supported" for c in review["claims"])


def test_audit_chain_detects_tampering(api: TestClient, session: Session) -> None:
    create(api, login(api, "usr_abhi1"), "sample_clean", "linkedin")
    assert audit.verify_chain(session).intact
    session.execute(
        text(
            "UPDATE audit_events SET payload_json = '{\"forged\": true}' "
            "WHERE id = (SELECT min(id) FROM audit_events)"
        )
    )
    status = audit.verify_chain(session)
    assert not status.intact
    assert status.broken_at is not None


def test_events_stream_replays_completed_review(api: TestClient) -> None:
    riya = login(api, "usr_abhi1")
    review = create(api, riya, "sample_clean", "linkedin")
    token = riya["Authorization"].removeprefix("Bearer ")
    with api.stream("GET", f"/api/reviews/{review['submission']['id']}/events?token={token}") as r:
        body = "".join(r.iter_text())
    assert "event: review_complete" in body


def test_receipt_is_issued_only_after_approval(api: TestClient) -> None:
    riya, neha = login(api, "usr_abhi1"), login(api, "usr_abhi4")
    review = create(api, riya, "sample_clean", "linkedin")
    review_id = review["submission"]["id"]
    assert api.get(f"/api/receipts/{review_id}").status_code == 409
    api.post(f"/api/reviews/{review_id}/transition", json={"action": "submit"}, headers=riya)
    api.post(f"/api/reviews/{review_id}/transition", json={"action": "approve"}, headers=neha)
    receipt = api.get(f"/api/receipts/{review_id}").json()
    assert receipt["audit_intact"] is True
    assert receipt["approver"]["id"] == "usr_abhi4"
    assert receipt["final_score"] == review["revision"]["brand_score"]
    pdf = api.get(f"/api/receipts/{review_id}/pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
