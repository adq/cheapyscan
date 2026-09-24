# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""A stand-in for the board that speaks the same serial protocol.

It replies to the same commands with the same strings as firmware/src/main.c
and finishes moves after the time the real motor would take. It is used by
`cheapyscan serve --simulate` and by the tests, so the web UI and a whole scan
can run with nothing plugged in.

`time_scale` shortens every move, so tests do not wait for real motor time.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from .firmware import RATE_MAX, RATE_MIN, STEP_COUNT_MAX

DEFAULT_RATE = 400


class _Axis:
    def __init__(self) -> None:
        self.base = 0  # position when the current move started
        self.steps = 0  # signed length of the current move
        self.rate = 0
        self.start = 0.0
        self.busy = False
        self.hold = True
        self.task: asyncio.Task | None = None

    def position(self, time_scale: float) -> int:
        if not self.busy:
            return self.base
        elapsed = (time.monotonic() - self.start) / time_scale
        done = min(abs(self.steps), int(elapsed * self.rate))
        return self.base + (done if self.steps > 0 else -done)


class SimulatedTransport:
    def __init__(self, time_scale: float = 1.0, boot_delay: float = 0.3):
        self.time_scale = time_scale
        self.boot_delay = boot_delay
        self.axes = {"X": _Axis(), "Y": _Axis()}
        self.sent: list[str] = []
        self._on_line: Callable[[str], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    def start(self, on_line: Callable[[str], None]) -> None:
        self._on_line = on_line
        self._loop = asyncio.get_running_loop()
        self._loop.call_later(self.boot_delay, self._emit, "cheapyscan ready")

    def close(self) -> None:
        self._closed = True
        for ax in self.axes.values():
            if ax.task:
                ax.task.cancel()

    def _emit(self, line: str) -> None:
        if not self._closed and self._on_line:
            self._on_line(line)

    def write_line(self, line: str) -> None:
        self.sent.append(line)
        if len(line) >= 48:
            return  # the firmware drops overlong lines with no reply
        reply = self._handle(line)
        if reply is not None:
            # Replies arrive after a serial round trip, never synchronously.
            assert self._loop
            self._loop.call_soon(self._emit, reply)

    def _handle(self, line: str) -> str | None:
        tokens = line.split()
        if not tokens:
            return None
        cmd = tokens[0].upper()
        args = tokens[1:]
        if cmd == "M":
            return self._move(args)
        if cmd == "S":
            if args:
                return "err unexpected argument"
            x, y = self.axes["X"], self.axes["Y"]
            ts = self.time_scale
            return (
                f"pos X={x.position(ts)} Y={y.position(ts)} "
                f"busy X={int(x.busy)} Y={int(y.busy)} "
                f"hold X={int(x.hold)} Y={int(y.hold)}"
            )
        if cmd == "Z":
            if not args:
                for ax in self.axes.values():
                    self._rebase(ax, 0)
                return "ok"
            ax = self.axes.get(args[0].upper())
            if ax is None or len(args) > 1:
                return "err axis"
            self._rebase(ax, 0)
            return "ok"
        if cmd == "H":
            if not args or args[0].upper() not in self.axes:
                return "err axis"
            if len(args) != 2 or args[1] not in ("0", "1"):
                return "err expected 0 or 1"
            self.axes[args[0].upper()].hold = args[1] == "1"
            return "ok"
        if cmd == "A":
            for ax in self.axes.values():
                if ax.busy:
                    self._stop(ax)
            return "ok"
        if cmd.startswith("?"):
            return None
        return "err unknown command"

    def _rebase(self, ax: _Axis, value: int) -> None:
        # `Z` mid-move resets the counter while stepping carries on.
        if ax.busy:
            moved = ax.position(self.time_scale) - ax.base
            ax.base = value - moved
        else:
            ax.base = value

    def _move(self, args: list[str]) -> str:
        if not args or args[0].upper() not in self.axes:
            return "err axis"
        name = args[0].upper()
        if len(args) < 2:
            return "err steps"
        try:
            steps = int(args[1])
        except ValueError:
            return "err steps"
        if abs(steps) > STEP_COUNT_MAX:
            return "err steps"
        rate = DEFAULT_RATE
        if len(args) >= 3:
            try:
                rate = int(args[2])
            except ValueError:
                return "err rate"
            if len(args) > 3:
                return "err rate"
            if rate < RATE_MIN or rate > RATE_MAX:
                return "err rate range"
        ax = self.axes[name]
        if ax.busy:
            return "err busy"
        if steps == 0:
            return "err steps range"
        ax.steps = steps
        ax.rate = rate
        ax.start = time.monotonic()
        ax.busy = True
        duration = abs(steps) / rate * self.time_scale
        ax.task = asyncio.get_running_loop().create_task(self._finish(name, duration))
        return "ok"

    def _stop(self, ax: _Axis) -> None:
        ax.base = ax.position(self.time_scale)
        ax.busy = False
        if ax.task:
            ax.task.cancel()
            ax.task = None

    async def _finish(self, name: str, duration: float) -> None:
        ax = self.axes[name]
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            # Aborted: the firmware still reports done for that axis.
            self._loop.call_soon(self._emit, f"done {name}")  # type: ignore[union-attr]
            raise
        ax.base += ax.steps
        ax.busy = False
        ax.task = None
        self._emit(f"done {name}")
