"""In-process event bus for live review progress (streamed to the browser over SSE).

Reviews run in a worker thread; events are handed to the API's event loop thread-safely.
Each revision keeps a short history so a client that connects late (or reloads the page)
still sees every step. Histories of finished reviews are dropped once there are many.
"""

import asyncio
import threading
from collections import defaultdict
from typing import Any

Event = tuple[str, dict[str, Any]]
TERMINAL = "review_complete"
MAX_HISTORIES = 2000


class EventBus:
    def __init__(self) -> None:
        self._history: dict[str, list[Event]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue[Event]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, key: str, event: str, data: dict[str, Any]) -> None:
        """Safe to call from any thread."""
        with self._lock:
            self._history[key].append((event, data))
            queues = list(self._subscribers[key])
            if len(self._history) > MAX_HISTORIES:
                self._trim()
        for queue in queues:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(queue.put_nowait, (event, data))

    def _trim(self) -> None:
        """Forget the oldest finished reviews nobody is watching (caller holds the lock)."""
        for old in list(self._history)[: len(self._history) - MAX_HISTORIES]:
            done = any(e == TERMINAL for e, _ in self._history[old])
            if done and not self._subscribers.get(old):
                del self._history[old]
                self._subscribers.pop(old, None)

    def subscribe(self, key: str) -> tuple[list[Event], asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        with self._lock:
            history = list(self._history[key])
            self._subscribers[key].append(queue)
        return history, queue

    def unsubscribe(self, key: str, queue: asyncio.Queue[Event]) -> None:
        with self._lock:
            if queue in self._subscribers[key]:
                self._subscribers[key].remove(queue)

    def finished(self, key: str) -> bool:
        with self._lock:
            return any(e == TERMINAL for e, _ in self._history[key])


bus = EventBus()
