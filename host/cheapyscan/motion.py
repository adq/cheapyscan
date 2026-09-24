# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Degrees on the host side, steps on the firmware side.

Angles follow OpenScan3: theta is the rotor angle, where 90 means the object
sits level, and phi is the turntable angle. The firmware counter is the only
record of position, so every target is converted to an absolute step count
from that counter rather than accumulated as relative moves. That way rounding
never builds up over a 130 point scan.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .config import AxisSettings
from .firmware import FirmwareClient, FirmwareError, Status

log = logging.getLogger(__name__)


class MotionError(Exception):
    pass


@dataclass
class Axis:
    name: str  # "rotor" or "turntable"
    cfg: AxisSettings
    wraps: bool  # turntable: takes the short way round across 0/360

    @property
    def sign(self) -> int:
        return -1 if self.cfg.invert else 1

    def steps_to_angle(self, steps: int) -> float:
        angle = self.cfg.reference_angle + steps * self.sign * 360.0 / self.cfg.steps_per_rev
        return angle % 360.0 if self.wraps else angle

    def clamp(self, angle: float) -> float:
        if self.wraps:
            return angle % 360.0
        return max(self.cfg.min_angle, min(self.cfg.max_angle, angle))

    def target_steps(self, current_steps: int, angle: float) -> int:
        """Absolute step count for `angle`, starting from `current_steps`."""
        if self.wraps:
            current = self.steps_to_angle(current_steps)
            delta = (angle - current + 180.0) % 360.0 - 180.0
            # Measure from the exact angle of the current count so a series
            # of wrapped moves stays on the same step grid.
            return current_steps + round(delta * self.cfg.steps_per_rev / 360.0) * self.sign
        return round((angle - self.cfg.reference_angle) * self.cfg.steps_per_rev / 360.0) * self.sign

    def move_time(self, from_angle: float, to_angle: float) -> float:
        """Seconds a move takes at this axis's constant rate."""
        d = abs(to_angle - from_angle)
        if self.wraps:
            d = d % 360.0
            d = min(d, 360.0 - d)
        return d * self.cfg.steps_per_rev / 360.0 / self.cfg.rate


class Motion:
    def __init__(self, fw: FirmwareClient, rotor: AxisSettings, turntable: AxisSettings):
        self.fw = fw
        self.rotor = Axis("rotor", rotor, wraps=False)
        self.turntable = Axis("turntable", turntable, wraps=True)
        self.referenced = False
        self.status: Status | None = None
        self.moving = False

    def configure(self, rotor: AxisSettings, turntable: AxisSettings) -> None:
        self.rotor.cfg = rotor
        self.turntable.cfg = turntable

    def axis(self, name: str) -> Axis:
        if name == "rotor":
            return self.rotor
        if name == "turntable":
            return self.turntable
        raise MotionError(f"unknown axis {name!r}")

    def _steps(self, ax: Axis) -> int:
        assert self.status
        return self.status.pos[ax.cfg.firmware_axis]

    def angles(self) -> dict[str, float] | None:
        if not self.status:
            return None
        return {
            "theta": self.rotor.steps_to_angle(self._steps(self.rotor)),
            "phi": self.turntable.steps_to_angle(self._steps(self.turntable)),
        }

    async def refresh(self) -> Status:
        self.status = await self.fw.status()
        return self.status

    async def set_reference(self) -> None:
        """Declare the current physical position to be the reference angles."""
        await self.fw.zero()
        await self.refresh()
        self.referenced = True

    async def set_hold(self, name: str, on: bool) -> None:
        await self.fw.hold(self.axis(name).cfg.firmware_axis, on)
        await self.refresh()

    async def abort(self) -> None:
        await self.fw.abort()
        await self.refresh()

    async def move_to(
        self, theta: float | None = None, phi: float | None = None
    ) -> dict[str, float]:
        """Move either or both axes together and wait until both stop."""
        await self.refresh()
        plan: list[tuple[Axis, int]] = []
        for ax, angle in ((self.rotor, theta), (self.turntable, phi)):
            if angle is None:
                continue
            clamped = ax.clamp(angle)
            if not ax.wraps and clamped != angle:
                log.warning("%s target %.2f clamped to %.2f", ax.name, angle, clamped)
            plan.append((ax, ax.target_steps(self._steps(ax), clamped)))
        return await self._run(plan)

    async def move_by(self, name: str, degrees: float) -> dict[str, float]:
        """Relative move. The turntable goes the way asked, even past 180."""
        await self.refresh()
        angles = self.angles()
        assert angles
        if name == "rotor":
            return await self.move_to(theta=angles["theta"] + degrees)
        ax = self.turntable
        delta = round(degrees * ax.cfg.steps_per_rev / 360.0) * ax.sign
        return await self._run([(ax, self._steps(ax) + delta)])

    async def _run(self, plan: list[tuple[Axis, int]]) -> dict[str, float]:
        if self.rotor.cfg.firmware_axis == self.turntable.cfg.firmware_axis:
            raise MotionError("rotor and turntable are set to the same firmware axis")
        self.moving = True
        try:
            waits = []
            for ax, target in plan:
                delta = target - self._steps(ax)
                fut = await self.fw.move(ax.cfg.firmware_axis, delta, ax.cfg.rate)
                timeout = abs(delta) / ax.cfg.rate * 1.5 + 2.0
                waits.append(asyncio.wait_for(fut, timeout))
            try:
                await asyncio.gather(*waits)
            except asyncio.TimeoutError:
                await self.fw.abort()
                raise MotionError(
                    "A move took far longer than expected and was aborted."
                ) from None
        finally:
            self.moving = False
            try:
                await self.refresh()
            except FirmwareError:
                pass

        # `done` also follows an abort, so check the counters hit the target.
        for ax, target in plan:
            if self._steps(ax) != target:
                raise MotionError(
                    f"The {ax.name} stopped at step {self._steps(ax)}, "
                    f"not {target}. The move was aborted."
                )
        angles = self.angles()
        assert angles
        return angles
