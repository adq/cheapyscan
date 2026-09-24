# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Async client for the cheapyscan firmware serial protocol.

The protocol is documented in firmware/README.md. In short, each command gets
exactly one reply line (`ok`, `err ...` or `pos ...`), and a finished move
sends `done <axis>` whenever the motor happens to stop. So replies are matched
to the one command in flight, and `done` lines are routed to per-axis futures.

Two quirks shape this code:
- `A` (abort) still produces a `done` later, so a `done` does not mean the
  move reached its target. Callers read the position with `status()` after.
- A line of 48 characters or more is dropped by the firmware with no reply,
  so this client refuses to send one rather than waiting forever.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass
from typing import Callable, Protocol

log = logging.getLogger(__name__)

BAUD = 115200
LINE_MAX = 47
STEP_COUNT_MAX = 1_000_000
RATE_MIN = 10
RATE_MAX = 4000
AXES = ("X", "Y")

# USB identifiers seen on genuine Arduino boards and the common clones. Used
# only to pick the likeliest port when several are present.
LIKELY_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}

_POS_RE = re.compile(
    r"pos X=(-?\d+) Y=(-?\d+) busy X=([01]) Y=([01]) hold X=([01]) Y=([01])"
)


class FirmwareError(Exception):
    """The firmware replied `err ...`, or did not reply at all."""


@dataclass(frozen=True)
class Status:
    pos: dict[str, int]
    busy: dict[str, bool]
    hold: dict[str, bool]


def parse_status(line: str) -> Status:
    m = _POS_RE.fullmatch(line.strip())
    if not m:
        raise FirmwareError(f"unexpected status line: {line!r}")
    g = m.groups()
    return Status(
        pos={"X": int(g[0]), "Y": int(g[1])},
        busy={"X": g[2] == "1", "Y": g[3] == "1"},
        hold={"X": g[4] == "1", "Y": g[5] == "1"},
    )


class Transport(Protocol):
    """A line-oriented link to the board: real serial port or the simulator."""

    def start(self, on_line: Callable[[str], None]) -> None: ...
    def write_line(self, line: str) -> None: ...
    def close(self) -> None: ...


class SerialTransport:
    """pyserial with a reader thread, handing lines to the asyncio loop."""

    def __init__(self, port: str):
        import serial

        self.port = port
        # Opening the port asserts DTR, which resets the board. That is
        # expected: the client waits for the `ready` banner afterwards.
        self._serial = serial.Serial(port, BAUD, timeout=0.1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_line: Callable[[str], None]) -> None:
        loop = asyncio.get_running_loop()

        def read_loop() -> None:
            import serial

            buf = b""
            while not self._stop.is_set():
                try:
                    chunk = self._serial.read(256)
                except (serial.SerialException, OSError) as e:
                    loop.call_soon_threadsafe(on_line, f"__closed__ {e}")
                    return
                if not chunk:
                    continue
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip()
                    if line:
                        loop.call_soon_threadsafe(on_line, line)

        self._thread = threading.Thread(target=read_loop, daemon=True)
        self._thread.start()

    def write_line(self, line: str) -> None:
        self._serial.write((line + "\n").encode("ascii"))
        self._serial.flush()

    def close(self) -> None:
        self._stop.set()
        try:
            self._serial.close()
        except Exception:
            pass


def list_ports() -> list[dict]:
    from serial.tools import list_ports as lp

    return [
        {
            "device": p.device,
            "description": p.description,
            "likely": p.vid in LIKELY_VIDS,
        }
        for p in lp.comports()
    ]


def find_port() -> str:
    """Pick the board's port, or explain why that is not possible."""
    ports = list_ports()
    if not ports:
        raise FirmwareError(
            "No serial ports found. Plug the board in and check it appears "
            "as /dev/ttyACM* or /dev/ttyUSB*. A charge-only USB cable carries "
            "power but no data."
        )
    candidates = [p for p in ports if p["likely"]] or ports
    if len(candidates) == 1:
        return candidates[0]["device"]
    names = ", ".join(p["device"] for p in candidates)
    raise FirmwareError(
        f"More than one serial port found ({names}). Choose one on the "
        "Settings page."
    )


class FirmwareClient:
    def __init__(self, transport: Transport, reply_timeout: float = 2.0):
        self._transport = transport
        self._reply_timeout = reply_timeout
        self._lock = asyncio.Lock()
        self._reply: asyncio.Future[str] | None = None
        self._ready = asyncio.Event()
        self._done: dict[str, asyncio.Future[None] | None] = {a: None for a in AXES}
        self._closed_reason: str | None = None
        self.on_disconnect: Callable[[str], None] | None = None

    @property
    def connected(self) -> bool:
        return self._closed_reason is None

    async def connect(self, banner_timeout: float = 6.0) -> None:
        self._transport.start(self._on_line)
        try:
            await asyncio.wait_for(self._ready.wait(), banner_timeout)
        except asyncio.TimeoutError:
            self.close()
            raise FirmwareError(
                f"The board did not send its ready banner within "
                f"{banner_timeout:.0f} s. Check it is running the cheapyscan "
                "firmware (firmware/scripts/flash.sh)."
            ) from None

    def close(self) -> None:
        self._transport.close()
        self._fail_all("connection closed")

    def _fail_all(self, reason: str) -> None:
        if self._closed_reason is None:
            self._closed_reason = reason
        err = FirmwareError(reason)
        if self._reply and not self._reply.done():
            self._reply.set_exception(err)
        for axis, fut in self._done.items():
            if fut and not fut.done():
                fut.set_exception(err)
                # Nobody may be awaiting it yet; stop asyncio warning.
                fut.exception()
            self._done[axis] = None

    def _on_line(self, line: str) -> None:
        if line.startswith("__closed__"):
            reason = "serial port closed: " + line[len("__closed__"):].strip()
            log.warning(reason)
            self._fail_all(reason)
            if self.on_disconnect:
                self.on_disconnect(reason)
            return
        log.debug("< %s", line)
        if line.endswith("ready"):
            self._ready.set()
            return
        if line.startswith("done "):
            axis = line[5:].strip().upper()
            fut = self._done.get(axis)
            if fut and not fut.done():
                fut.set_result(None)
            self._done[axis] = None
            return
        if line == "ok" or line.startswith("err") or line.startswith("pos "):
            if self._reply and not self._reply.done():
                self._reply.set_result(line)
            else:
                log.warning("reply with no command waiting: %s", line)
            return
        # Help text or anything else unsolicited.
        log.debug("ignored line: %s", line)

    async def _command(self, line: str) -> str:
        if len(line) > LINE_MAX:
            raise FirmwareError(f"command too long for the firmware: {line!r}")
        if self._closed_reason:
            raise FirmwareError(self._closed_reason)
        async with self._lock:
            loop = asyncio.get_running_loop()
            self._reply = loop.create_future()
            log.debug("> %s", line)
            self._transport.write_line(line)
            try:
                reply = await asyncio.wait_for(self._reply, self._reply_timeout)
            except asyncio.TimeoutError:
                raise FirmwareError(f"no reply to {line!r}") from None
            finally:
                self._reply = None
        if reply.startswith("err"):
            raise FirmwareError(f"{line!r} failed: {reply}")
        return reply

    async def move(self, axis: str, steps: int, rate: int) -> asyncio.Future[None]:
        """Start a relative move. Returns a future that completes on `done`.

        Zero steps is not a move to the firmware (`err steps range`), so it
        returns an already completed future instead.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        if steps == 0:
            fut.set_result(None)
            return fut
        if abs(steps) > STEP_COUNT_MAX:
            raise FirmwareError(f"move of {steps} steps exceeds {STEP_COUNT_MAX}")
        rate = max(RATE_MIN, min(RATE_MAX, int(rate)))
        # Arm the future before sending, because a short move can report
        # `done` before this coroutine resumes.
        self._done[axis] = fut
        try:
            await self._command(f"M {axis} {steps} {rate}")
        except BaseException:
            if self._done[axis] is fut:
                self._done[axis] = None
            raise
        return fut

    async def status(self) -> Status:
        return parse_status(await self._command("S"))

    async def zero(self, axis: str | None = None) -> None:
        await self._command(f"Z {axis}" if axis else "Z")

    async def hold(self, axis: str, on: bool) -> None:
        await self._command(f"H {axis} {1 if on else 0}")

    async def abort(self) -> None:
        await self._command("A")
