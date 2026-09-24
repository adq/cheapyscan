# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""The whole rig as one object: board, motors, camera, projects, scan.

The web API is a thin layer over this class, and the tests drive it directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from . import cameras, config
from .cameras import Camera, CameraError
from .events import EventBus
from .firmware import FirmwareClient, FirmwareError, SerialTransport, Transport, find_port
from .motion import Motion, MotionError
from .path import Point, fibonacci_path, nearest_neighbour, total_time
from .projects import Projects, ProjectError, read_json, write_json
from .scan import ScanTask, path_entries, points_from_entries
from .simulator import SimulatedTransport

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.25


class RigError(Exception):
    """Something the user can fix. The message says how."""


class Rig:
    def __init__(
        self,
        settings: config.Settings,
        config_path: Path | None = None,
        simulate: bool = False,
        sim_time_scale: float = 1.0,
    ):
        self.settings = settings
        self.config_path = config_path
        self.simulate = simulate
        self.sim_time_scale = sim_time_scale
        self.bus = EventBus()
        self.fw: FirmwareClient | None = None
        self.motion: Motion | None = None
        self.port: str | None = None
        self.camera: Camera | None = None
        self.scan: ScanTask | None = None
        self._poller: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()

    @property
    def projects(self) -> Projects:
        return Projects(Path(self.settings.projects_dir).expanduser())

    # ---- settings ----------------------------------------------------------

    def update_settings(self, new: config.Settings) -> None:
        if new.rotor.firmware_axis == new.turntable.firmware_axis:
            raise RigError("The rotor and turntable must use different firmware axes.")
        if self.scan and self.scan.active:
            raise RigError("Settings cannot change while a scan is running.")
        camera_changed = new.camera != self.settings.camera
        axes_changed = (
            new.rotor.firmware_axis != self.settings.rotor.firmware_axis
            or new.turntable.firmware_axis != self.settings.turntable.firmware_axis
            or new.rotor.reference_angle != self.settings.rotor.reference_angle
            or new.turntable.reference_angle != self.settings.turntable.reference_angle
            or new.rotor.steps_per_rev != self.settings.rotor.steps_per_rev
            or new.turntable.steps_per_rev != self.settings.turntable.steps_per_rev
            or new.rotor.invert != self.settings.rotor.invert
            or new.turntable.invert != self.settings.turntable.invert
        )
        self.settings = new
        if self.config_path:
            config.save(new, self.config_path)
        if self.motion:
            self.motion.configure(new.rotor, new.turntable)
            if axes_changed:
                # The step counts now mean different angles.
                self.motion.referenced = False
        if camera_changed:
            self._close_camera()
        self.publish_status()

    # ---- status ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        m = self.motion
        return {
            "connected": bool(self.fw and self.fw.connected),
            "simulate": self.simulate,
            "port": self.port,
            "referenced": bool(m and m.referenced),
            "moving": bool(m and m.moving),
            "angles": m.angles() if m else None,
            "hold": (
                {
                    "rotor": m.status.hold[m.rotor.cfg.firmware_axis],
                    "turntable": m.status.hold[m.turntable.cfg.firmware_axis],
                }
                if m and m.status
                else None
            ),
            "camera": {
                "backend": self.camera_backend(),
                "connected": self.camera is not None,
            },
            "scan": self.scan.snapshot() if self.scan else None,
        }

    def publish_status(self) -> None:
        self.bus.publish("status", status=self.status())

    def camera_backend(self) -> str:
        return "dummy" if self.simulate else self.settings.camera.backend

    # ---- board -------------------------------------------------------------

    async def connect(self) -> None:
        async with self._connect_lock:
            if self.fw and self.fw.connected:
                return
            transport: Transport
            if self.simulate:
                transport = SimulatedTransport(time_scale=self.sim_time_scale, boot_delay=0.05)
                self.port = "simulator"
            else:
                try:
                    port = self.settings.serial_port or find_port()
                except FirmwareError as e:
                    raise RigError(str(e)) from e
                try:
                    transport = SerialTransport(port)
                except Exception as e:
                    raise RigError(_serial_hint(port, e)) from e
                self.port = port
            fw = FirmwareClient(transport)
            fw.on_disconnect = lambda reason: self._on_disconnect(reason)
            try:
                await fw.connect()
            except FirmwareError as e:
                raise RigError(str(e)) from e
            self.fw = fw
            self.motion = Motion(fw, self.settings.rotor, self.settings.turntable)
            await self.motion.refresh()
            self._poller = asyncio.create_task(self._poll())
            self.bus.publish("log", level="info", message=f"Connected to the board on {self.port}.")
            self.publish_status()

    async def disconnect(self) -> None:
        if self.scan and self.scan.active:
            raise RigError("Stop the scan before disconnecting.")
        if self._poller:
            self._poller.cancel()
            self._poller = None
        if self.fw:
            self.fw.close()
        self.fw = None
        self.motion = None
        self.port = None
        self.publish_status()

    def _on_disconnect(self, reason: str) -> None:
        self.bus.publish("log", level="error", message=f"Lost the board: {reason}")
        if self.scan and self.scan.active:
            self.scan.cancel()
        self.publish_status()

    async def _poll(self) -> None:
        """Report positions while the motors move, for the live 3D view."""
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            m = self.motion
            if not m or not self.fw or not self.fw.connected or not m.moving:
                continue
            try:
                await m.refresh()
            except FirmwareError:
                continue
            self.bus.publish("position", angles=m.angles(), moving=True)

    def require_motion(self, manual: bool = True) -> Motion:
        if not self.motion or not self.fw or not self.fw.connected:
            raise RigError("The board is not connected.")
        if manual and self.scan and self.scan.active:
            raise RigError("The motors are under the scan's control. Pause or cancel it first.")
        return self.motion

    async def _motion_call(self, coro) -> dict[str, Any]:
        try:
            await coro
        except (FirmwareError, MotionError) as e:
            raise RigError(str(e)) from e
        finally:
            self.publish_status()
        return self.status()

    async def move_to(self, theta: float | None, phi: float | None) -> dict[str, Any]:
        m = self.require_motion()
        return await self._motion_call(m.move_to(theta, phi))

    async def move_by(self, axis: str, degrees: float) -> dict[str, Any]:
        m = self.require_motion()
        return await self._motion_call(m.move_by(axis, degrees))

    async def set_reference(self) -> dict[str, Any]:
        m = self.require_motion()
        return await self._motion_call(m.set_reference())

    async def set_hold(self, axis: str, on: bool) -> dict[str, Any]:
        m = self.require_motion()
        return await self._motion_call(m.set_hold(axis, on))

    async def abort(self) -> dict[str, Any]:
        """Stop both motors now. Also stops a running scan."""
        if self.scan and self.scan.active:
            self.scan.cancel()
        m = self.require_motion(manual=False)
        return await self._motion_call(m.abort())

    # ---- camera ------------------------------------------------------------

    async def get_camera(self) -> Camera:
        if self.camera is None:
            name = self.camera_backend()
            same = name == self.settings.camera.backend
            opts = self.settings.camera.options if same else {}
            try:
                cam = cameras.create(name, opts)
                await asyncio.to_thread(cam.connect)
            except CameraError as e:
                raise RigError(str(e)) from e
            self.camera = cam
            self.publish_status()
        return self.camera

    def _close_camera(self) -> None:
        if self.camera:
            try:
                self.camera.close()
            except Exception:
                pass
            self.camera = None

    async def camera_info(self) -> dict[str, Any]:
        cam = await self.get_camera()
        try:
            return await asyncio.to_thread(cam.info)
        except CameraError as e:
            self._close_camera()
            raise RigError(str(e)) from e

    async def test_capture(self) -> dict[str, Any]:
        """One photo into <projects>/_test, returned as a file name."""
        if self.scan and self.scan.active:
            raise RigError("The camera is in use by the scan.")
        cam = await self.get_camera()
        dest = Path(self.settings.projects_dir).expanduser() / "_test"
        stem = time.strftime("test_%Y%m%d_%H%M%S")
        angles = self.motion.angles() if self.motion else None
        try:
            files = await asyncio.to_thread(cam.capture, dest, stem, angles or {})
        except CameraError as e:
            self._close_camera()
            raise RigError(str(e)) from e
        return {"files": [f.name for f in files]}

    def test_photo_path(self, filename: str) -> Path:
        dest = Path(self.settings.projects_dir).expanduser() / "_test"
        p = dest / filename
        if "/" in filename or not p.is_file():
            raise RigError("No such test photo.")
        return p

    # ---- scans -------------------------------------------------------------

    def plan_path(self, s: config.ScanSettings, start: dict[str, float] | None = None) -> list[Point]:
        if s.min_theta > s.max_theta:
            raise RigError("The minimum rotor angle is above the maximum.")
        r = self.settings.rotor
        if s.min_theta < r.min_angle or s.max_theta > r.max_angle:
            raise RigError(
                f"The scan's rotor range {s.min_theta:g} to {s.max_theta:g} is "
                f"outside the rotor limits {r.min_angle:g} to {r.max_angle:g}."
            )
        points = fibonacci_path(s.points, s.min_theta, s.max_theta, s.min_phi, s.max_phi)
        if s.optimize_path:
            start = start or {"theta": r.reference_angle, "phi": self.settings.turntable.reference_angle}
            points = nearest_neighbour(points, start["theta"], start["phi"], self.move_cost)
        return points

    def move_cost(self, t0: float, p0: float, t1: float, p1: float) -> float:
        from .motion import Axis

        rot = Axis("rotor", self.settings.rotor, wraps=False)
        tt = Axis("turntable", self.settings.turntable, wraps=True)
        return max(rot.move_time(t0, t1), tt.move_time(p0, p1))

    def preview_path(self, s: config.ScanSettings) -> dict[str, Any]:
        start = self.motion.angles() if self.motion and self.motion.status else None
        points = self.plan_path(s, start)
        start = start or {"theta": self.settings.rotor.reference_angle, "phi": self.settings.turntable.reference_angle}
        move_s = total_time(points, start["theta"], start["phi"], self.move_cost)
        return {
            "points": path_entries(points),
            "move_time_s": move_s,
            "settle_time_s": s.settle_ms / 1000 * len(points),
        }

    def _check_can_scan(self) -> Motion:
        if self.scan and self.scan.active:
            raise RigError("A scan is already running.")
        m = self.require_motion(manual=False)
        if not m.referenced:
            raise RigError(
                "Set the reference position on the Control page first, so the "
                "rig knows where the motors are."
            )
        return m

    async def start_scan(self, project: str, s: config.ScanSettings) -> dict[str, Any]:
        m = self._check_can_scan()
        cam = await self.get_camera()
        try:
            self.projects.project_dir(project)
            points = self.plan_path(s, m.angles())
            index, sdir = self.projects.new_scan(project)
        except ProjectError as e:
            raise RigError(str(e)) from e
        write_json(sdir / "path.json", path_entries(points))
        record = {
            "index": index,
            "project": project,
            "settings": s.model_dump(),
            "camera_backend": self.camera_backend(),
            "created": time.time(),
            "duration_s": 0.0,
        }
        return self._launch(m, cam, project, index, sdir, s, points, 0, record)

    async def resume_scan(self, project: str, index: int) -> dict[str, Any]:
        m = self._check_can_scan()
        cam = await self.get_camera()
        try:
            sdir = self.projects.scan_dir(project, index)
        except ProjectError as e:
            raise RigError(str(e)) from e
        record = read_json(sdir / "scan.json")
        if record.get("status") == "completed":
            raise RigError("That scan is already complete.")
        points = points_from_entries(read_json(sdir / "path.json"))
        s = config.ScanSettings.model_validate(record["settings"])
        return self._launch(m, cam, project, index, sdir, s, points, int(record.get("current_step", 0)), record)

    def _launch(self, m, cam, project, index, sdir, s, points, start_step, record) -> dict[str, Any]:
        self.scan = ScanTask(
            motion=m,
            camera=cam,
            projects=self.projects,
            bus=self.bus,
            project=project,
            scan_index=index,
            scan_dir=sdir,
            settings=s,
            points=points,
            start_step=start_step,
            end_position=self.settings.end_position,
            record=record,
        )
        task = self.scan.start()
        task.add_done_callback(lambda _t: self.publish_status())
        self.publish_status()
        return self.scan.snapshot()

    def active_scan(self, project: str, index: int) -> ScanTask:
        if not self.scan or self.scan.project != project or self.scan.scan_index != index or not self.scan.active:
            raise RigError("That scan is not running.")
        return self.scan

    async def shutdown(self) -> None:
        if self.scan and self.scan.active:
            self.scan.cancel()
            try:
                await asyncio.wait_for(self.scan.wait(), 30)
            except Exception:
                pass
        if self._poller:
            self._poller.cancel()
        if self.fw:
            self.fw.close()
        self._close_camera()


def _serial_hint(port: str, e: Exception) -> str:
    text = str(e)
    if "Permission denied" in text or "Errno 13" in text:
        return (
            f"No permission to open {port}. Add yourself to the serial group "
            "(uucp on Arch, dialout elsewhere) and log in again. "
            "firmware/scripts/setup-toolchain.sh does this."
        )
    if "Errno 16" in text or "busy" in text.lower():
        return f"{port} is in use by another program, such as tools/motor-console.py."
    return f"Could not open {port}: {text}"
