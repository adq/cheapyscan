# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""One scan: move to each point, wait for the object to settle, capture.

The sequence follows OpenScan3's scan task. For each point in the (possibly
reordered) path it moves both axes together, pauses, takes the photo, then
writes the photo's metadata and the scan's progress before moving on. At the
end, or on cancel, the rig goes to the end position.

Progress is saved after every photo. A scan that stops part way, for any
reason, can be resumed from the first point it had not photographed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from .cameras import Camera
from .config import EndPosition, ScanSettings
from .events import EventBus
from .motion import Motion
from .path import Point
from .projects import Projects, photo_stem, write_json

log = logging.getLogger(__name__)

CAPTURE_TIMEOUT_S = 60.0

ACTIVE = ("running", "paused", "cancelling")


def path_entries(points: list[Point]) -> list[dict[str, Any]]:
    out = []
    for step, p in enumerate(points):
        x, y, z = p.cartesian()
        out.append(
            {
                "execution_step": step,
                "original_step": p.index,
                "theta": round(p.theta, 4),
                "phi": round(p.phi, 4),
                "cartesian": {"x": round(x, 6), "y": round(y, 6), "z": round(z, 6)},
            }
        )
    return out


def points_from_entries(entries: list[dict[str, Any]]) -> list[Point]:
    return [Point(e["original_step"], e["theta"], e["phi"]) for e in entries]


class ScanTask:
    def __init__(
        self,
        *,
        motion: Motion,
        camera: Camera,
        projects: Projects,
        bus: EventBus,
        project: str,
        scan_index: int,
        scan_dir: Path,
        settings: ScanSettings,
        points: list[Point],
        start_step: int,
        end_position: EndPosition,
        record: dict[str, Any],
    ):
        self.motion = motion
        self.camera = camera
        self.projects = projects
        self.bus = bus
        self.project = project
        self.scan_index = scan_index
        self.scan_dir = scan_dir
        self.settings = settings
        self.points = points
        self.current_step = start_step
        self.end_position = end_position
        self.record = record
        self.state = "running"
        self.error: str | None = None
        self.last_photo: str | None = None
        self.phase = "starting"
        self._resume = asyncio.Event()
        self._resume.set()
        self._cancel = False
        self._task: asyncio.Task | None = None
        self._step_times: list[float] = []

    # ---- control -----------------------------------------------------------

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run())
        return self._task

    async def wait(self) -> None:
        if self._task:
            await self._task

    def pause(self) -> None:
        if self.state == "running":
            self.state = "paused"
            self._resume.clear()
            self._publish()

    def resume(self) -> None:
        if self.state == "paused":
            self.state = "running"
            self._resume.set()
            self._publish()

    def cancel(self) -> None:
        if self.state in ("running", "paused"):
            self._cancel = True
            self.state = "cancelling"
            self._resume.set()
            self._publish()

    @property
    def active(self) -> bool:
        return self.state in ACTIVE

    # ---- reporting ---------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        total = len(self.points)
        eta = None
        if self._step_times and self.active:
            recent = self._step_times[-10:]
            eta = sum(recent) / len(recent) * (total - self.current_step)
        return {
            "project": self.project,
            "scan_index": self.scan_index,
            "state": self.state,
            "phase": self.phase,
            "current_step": self.current_step,
            "total_steps": total,
            "eta_s": eta,
            "last_photo": self.last_photo,
            "error": self.error,
        }

    def _publish(self) -> None:
        self.bus.publish("scan", scan=self.snapshot())

    def _save_record(self, **changes: Any) -> None:
        self.record.update(changes)
        self.record["current_step"] = self.current_step
        self.record["total_steps"] = len(self.points)
        self.record["updated"] = time.time()
        write_json(self.scan_dir / "scan.json", self.record)

    # ---- the sequence ------------------------------------------------------

    async def _run(self) -> None:
        self._save_record(status="running", error=None)
        self._publish()
        try:
            while self.current_step < len(self.points):
                await self._resume.wait()
                if self._cancel:
                    break
                started = time.monotonic()
                await self._shoot(self.current_step, self.points[self.current_step])
                self.current_step += 1
                elapsed = time.monotonic() - started
                self._step_times.append(elapsed)
                duration = self.record.get("duration_s", 0.0) + elapsed
                self._save_record(duration_s=round(duration, 2))
                self._publish()
            final = "cancelled" if self._cancel else "completed"
        except asyncio.CancelledError:
            self.state = "cancelled"
            self._save_record(status="cancelled")
            raise
        except Exception as e:
            log.exception("scan failed")
            self.state = "failed"
            self.error = str(e)
            self.phase = "stopped"
            self._save_record(status="failed", error=self.error)
            self._publish()
            return

        self.phase = "returning"
        self._publish()
        try:
            await self.motion.move_to(self.end_position.theta, self.end_position.phi)
        except Exception as e:
            log.warning("could not return to the end position: %s", e)
        self.state = final
        self.phase = "stopped"
        self._save_record(status=final, finished=time.time())
        self._publish()

    async def _shoot(self, step: int, p: Point) -> None:
        self.phase = "moving"
        self._publish()
        actual = await self.motion.move_to(p.theta, p.phi)
        self.bus.publish("position", angles=actual, moving=False)

        if self.settings.settle_ms:
            self.phase = "settling"
            self._publish()
            await asyncio.sleep(self.settings.settle_ms / 1000)

        self.phase = "capturing"
        self._publish()
        stem = photo_stem(self.scan_index, p.index)
        context = {"theta": actual["theta"], "phi": actual["phi"], "step": p.index}
        files = await asyncio.wait_for(
            asyncio.to_thread(self.camera.capture, self.scan_dir, stem, context),
            CAPTURE_TIMEOUT_S,
        )
        if not files:
            raise RuntimeError("the camera returned no file")

        write_json(
            self.scan_dir / "metadata" / f"{stem}.json",
            {
                "step": p.index,
                "execution_step": step,
                "target": {"theta": p.theta, "phi": p.phi},
                "actual": actual,
                "files": [f.name for f in files],
                "captured": time.time(),
                "project": self.project,
                "scan_index": self.scan_index,
            },
        )
        self.last_photo = files[0].name
        try:
            self.projects.set_project_thumbnail(self.project, files[0])
        except Exception as e:
            log.warning("could not make the project thumbnail: %s", e)
        self.bus.publish(
            "photo",
            project=self.project,
            scan_index=self.scan_index,
            step=p.index,
            execution_step=step,
            files=[f.name for f in files],
        )
