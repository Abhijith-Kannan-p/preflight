from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app import db
from app.main import create_app
from app.ml import warmup


def test_health_ok_when_database_reachable_and_models_warm(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(db, "database_reachable", lambda: True)
    monkeypatch.setattr(warmup, "models_ready", lambda: True)
    body = TestClient(create_app()).get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["models_ready"] is True


def test_health_starting_while_models_load(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(db, "database_reachable", lambda: True)
    monkeypatch.setattr(warmup, "models_ready", lambda: False)
    assert TestClient(create_app()).get("/health").json()["status"] == "starting"


def test_health_degraded_when_database_down(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(db, "database_reachable", lambda: False)
    assert TestClient(create_app()).get("/health").json()["status"] == "degraded"
