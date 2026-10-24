from fastapi.testclient import TestClient


def test_lists_rules_with_source_refs(client: TestClient) -> None:
    rules = client.get("/api/rulebook/rules").json()
    clm04 = next(r for r in rules if r["code"] == "CLM-04")
    assert clm04["source_ref"] == "brand_book.pdf#p14"
    assert clm04["severity"] == "critical"


def test_lists_facts_with_validity(client: TestClient) -> None:
    facts = {f["id"]: f for f in client.get("/api/rulebook/facts").json()}
    assert facts["F-086"]["superseded_by"] == "F-087"
    assert facts["F-086"]["is_current"] is False
    assert "embedding" not in facts["F-087"]


def test_lists_terms_channels_confidential_and_voice(client: TestClient) -> None:
    terms = client.get("/api/rulebook/terms").json()
    assert any(t["term"] == "PayWise" and "Paywise" in t["variants"] for t in terms)
    channels = {c["id"]: c for c in client.get("/api/rulebook/channels").json()}
    assert channels["x"]["max_chars"] == 280
    confidential = [c["term"] for c in client.get("/api/rulebook/confidential").json()]
    assert "Project Falcon" in confidential
    voice = client.get("/api/rulebook/voice").json()
    assert set(voice["traits"]) == {"formal", "warm", "confident", "playful", "technical"}


def test_lists_users_and_samples(client: TestClient) -> None:
    roles = {u["role"] for u in client.get("/api/users").json()}
    assert {"creator", "brand_manager", "approver", "admin"} <= roles
    samples = client.get("/api/samples").json()
    assert samples[0]["content"].startswith("Say hello to India's #1")
