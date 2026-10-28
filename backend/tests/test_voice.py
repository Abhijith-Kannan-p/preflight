"""Voice Fingerprint: learned from approved content, adopted as a new voice-profile version."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.voice import lexical
from app.models import AuditEvent, Revision, Workspace
from tests.test_governance import api, clear, login, review

__all__ = ["api"]

PLAIN_POSTS = [
    "PayWise settles merchant payments in under 10 seconds.",
    "PayWise requires two-factor authentication for every login from a new device.",
    "PayWise Business supports UPI, cards and net banking.",
    "Our support team works in 12 Indian languages.",
    "PayWise Card works at any shop that accepts cards.",
]


def test_lexical_features_per_100_words() -> None:
    features = lexical("You can pay today! Your shop gets the best rates. It is simple.")
    assert features["sentence_words"] == round(13 / 3, 1)
    assert features["exclamations_per_100"] == round(100 / 13, 2)
    assert features["second_person_per_100"] == round(200 / 13, 2)
    assert features["superlatives_per_100"] == round(100 / 13, 2)
    # Words that merely end in -est are not superlatives.
    assert lexical("Earn interest on the latest request.")["superlatives_per_100"] == 0


def test_fingerprint_needs_enough_approved_items(api: TestClient) -> None:
    client = api  # the fixture runs reviews inline
    lead = login(client, "usr_abhi3")
    fp = client.get("/api/voice/fingerprint", headers=lead).json()
    assert fp["items"] < fp["min_items"] and not fp["ready"]  # the test seed has no history
    refused = client.post("/api/voice/adopt", headers=lead)
    assert refused.status_code == 409


def test_adopting_the_fingerprint_versions_the_profile_and_tone_uses_it(
    api: TestClient, session: Session
) -> None:
    client = api
    writer, approver = login(client, "usr_abhi1"), login(client, "usr_abhi4")
    lead = login(client, "usr_abhi3")
    for i, text in enumerate(PLAIN_POSTS):
        item = review(client, writer, text, f"Plain post {i}")
        clear(client, item["submission"]["id"], writer, approver)

    fp = client.get("/api/voice/fingerprint", headers=lead).json()
    assert fp["items"] >= len(PLAIN_POSTS)
    assert fp["ready"]
    assert fp["score_sources"].get("heuristic", 0) >= len(PLAIN_POSTS)
    assert set(fp["learned"]) == {"formal", "warm", "confident", "playful", "technical"}
    assert fp["replay"]["drafts"] >= len(PLAIN_POSTS)

    denied = client.post("/api/voice/adopt", headers=writer)
    assert denied.status_code == 403
    adopted = client.post("/api/voice/adopt", headers=lead)
    assert adopted.status_code == 200, adopted.text
    version = adopted.json()["version"]

    session.expire_all()
    workspace = session.scalars(select(Workspace)).first()
    assert workspace is not None
    learned = {t: v["value"] for t, v in fp["learned"].items()}
    assert workspace.voice_profile["traits"] == learned
    assert workspace.voice_profile["version"] == version
    assert workspace.settings["voice_history"][-1]["traits"] != learned
    assert session.scalars(
        select(AuditEvent).where(AuditEvent.action == "voice_profile_adopted")
    ).first()

    # The next review compares tone with the learned targets.
    after = review(client, writer, PLAIN_POSTS[0] + " Thank you.", "After adoption")
    revision = session.scalars(
        select(Revision).where(Revision.submission_id == after["submission"]["id"])
    ).one()
    assert revision.report["tone"]["targets"] == learned

    rates = client.get("/api/voice/fingerprint", headers=lead).json()["dispute_rate"]
    assert [row["version"] for row in rates["by_version"]][-1] == version
    assert rates["after"]["version"] == version
