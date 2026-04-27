"""In-memory pub/sub for live SSE events.

Single-process. If Carson is split across processes, replace with Redis
pubsub or similar without touching the rest of the app.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, event: dict[str, Any]) -> None:
        event = {"ts": time.time(), **event}
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self._subscribers.discard(q)

    @property
    def listener_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()


def serialize(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str)
