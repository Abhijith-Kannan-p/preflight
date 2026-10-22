from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app import db
from app.main import create_app


def test_health_ok_when_database_reachable(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(db, "database_reachable", lambda: True)
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_health_degraded_when_database_down(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(db, "database_reachable", lambda: False)
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
