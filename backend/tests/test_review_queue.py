"""The review job queue: order, queue positions, duplicate submits and the time budget."""

import threading
import time
from types import SimpleNamespace

import pytest

from app.services import runner
from app.services.events import TERMINAL, bus


@pytest.fixture
def one_worker(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    settings = SimpleNamespace(review_workers=1, review_timeout_seconds=5.0)
    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    return settings


def _events(key: str, name: str) -> list[dict[str, object]]:
    history, queue = bus.subscribe(key)
    bus.unsubscribe(key, queue)
    return [data for event, data in history if event == name]


def _wait_until(condition: object, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:  # type: ignore[operator]
        time.sleep(0.02)


def test_jobs_run_in_order_and_waiting_ones_know_their_position(
    one_worker: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    ran: list[str] = []

    def fake_run(revision_id: str) -> None:
        ran.append(revision_id)
        release.wait(5)

    monkeypatch.setattr(runner, "run_revision", fake_run)
    ids = [f"rev_queue_{n}" for n in range(3)]
    for revision_id in ids:
        runner.start_review(revision_id)
    _wait_until(lambda: ran == ids[:1])
    assert runner.queue_position(ids[0]) is None, "the first one is running"
    assert runner.queue_position(ids[1]) == 1
    assert runner.queue_position(ids[2]) == 2
    assert _events(ids[2], "queued")[-1] == {"position": 2, "ahead": 1}

    runner.start_review(ids[2])  # a double submit is ignored
    release.set()
    _wait_until(lambda: len(ran) == 3)
    assert ran == ids
    assert all(runner.queue_position(i) is None for i in ids)


def test_a_review_over_its_time_budget_fails_with_a_clear_message(
    one_worker: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    one_worker.review_timeout_seconds = 0.2
    stuck = threading.Event()
    monkeypatch.setattr(runner, "run_revision", lambda revision_id: stuck.wait(3))
    runner.start_review("rev_queue_slow")
    _wait_until(lambda: bool(_events("rev_queue_slow", TERMINAL)))
    final = _events("rev_queue_slow", TERMINAL)[-1]
    assert final["ok"] is False
    assert "Press Re-check" in str(final["error"])
    assert "rev_queue_slow" in runner._abandoned
    stuck.set()
