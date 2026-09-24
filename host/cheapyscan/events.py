# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""In-process publish and subscribe, feeding the web UI's WebSocket.

Each subscriber gets its own bounded queue. A browser tab that stops reading
loses its oldest events rather than holding up the scan.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


class EventBus:
    def __init__(self, maxsize: int = 500):
        self._subs: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, type_: str, **data: Any) -> None:
        event = {"type": type_, "time": time.time(), **data}
        for q in self._subs:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)
