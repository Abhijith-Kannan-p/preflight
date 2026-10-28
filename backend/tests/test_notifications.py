"""Notifications are pushed to the recipient's live stream when their transaction commits."""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Notification
from app.services.events import bus
from app.services.notify import NOTIFICATION_EVENT, stream_key


def test_committed_notifications_are_pushed_and_rolled_back_ones_are_not(
    session: Session,
) -> None:
    async def scenario() -> list[tuple[str, dict[str, object]]]:
        bus.bind(asyncio.get_running_loop())
        _history, queue = bus.subscribe(stream_key("usr_abhi1"))
        try:
            session.add(Notification(user_id="usr_abhi1", kind="test", message="dropped"))
            session.flush()
            session.rollback()
            session.add(Notification(user_id="usr_abhi1", kind="test", message="kept"))
            session.add(Notification(user_id="usr_abhi2", kind="test", message="other user"))
            session.commit()
            await asyncio.sleep(0)
            received = []
            while not queue.empty():
                received.append(queue.get_nowait())
            return received
        finally:
            bus.unsubscribe(stream_key("usr_abhi1"), queue)

    received = asyncio.run(scenario())
    assert [(name, data["kind"]) for name, data in received] == [(NOTIFICATION_EVENT, "test")]
    assert not bus.finished(stream_key("usr_abhi1")), "live only: nothing kept for replay"


def test_stream_rejects_a_bad_token(client: TestClient) -> None:
    assert client.get("/api/notifications/stream?token=nope").status_code == 401
