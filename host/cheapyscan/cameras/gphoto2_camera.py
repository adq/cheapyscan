# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""A camera tethered over USB through libgphoto2, such as the Nikon D90.

Each capture fires the shutter, downloads the new file into the scan folder
and, unless `keep_on_card` is set, leaves nothing on the camera. A camera set
to RAW + JPEG adds a second file a moment after the first, so the capture
waits briefly for any extra files before returning.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

from .base import Camera, CameraError, register

log = logging.getLogger(__name__)

try:
    import gphoto2 as gp
except ImportError:  # pragma: no cover - depends on the platform
    gp = None

# libgphoto2 error codes worth a specific explanation.
_ERR_MODEL_NOT_FOUND = -105
_ERR_IO_USB_CLAIM = -53
_ERR_CAMERA_BUSY = -110


def _explain(e: Exception) -> str:
    code = getattr(e, "code", None)
    if code == _ERR_MODEL_NOT_FOUND:
        return (
            "No camera found. Check the camera is on, connected by USB and not "
            "asleep. On the D90, turn the auto meter-off delay up so it stays "
            "awake between shots."
        )
    if code == _ERR_IO_USB_CLAIM:
        return (
            "Another program has the camera open. This is usually the desktop's "
            "file manager (gvfs). Close it or run: "
            "pkill -f gvfs-gphoto2-volume-monitor"
        )
    if code == _ERR_CAMERA_BUSY:
        return "The camera is busy. Wait for it to finish writing and try again."
    return f"gphoto2 error: {e}"


class GPhoto2Camera(Camera):
    description = "USB tethered camera through libgphoto2 (Nikon D90 and others)."
    default_options = {
        "keep_on_card": False,
        # How long to wait for a second file (RAW + JPEG) after a capture.
        "extra_file_wait_ms": 1500,
    }

    def __init__(self, options: dict[str, Any]):
        super().__init__(options)
        self._cam = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if gp is None:
            raise CameraError("python-gphoto2 is not installed on this platform.")
        with self._lock:
            if self._cam is not None:
                return
            cam = gp.Camera()
            try:
                cam.init()
            except gp.GPhoto2Error as e:
                raise CameraError(_explain(e)) from e
            self._cam = cam
            try:
                self._set_capture_target(bool(self.options["keep_on_card"]))
            except gp.GPhoto2Error as e:
                log.warning("could not set capture target: %s", e)

    def close(self) -> None:
        with self._lock:
            if self._cam is not None:
                try:
                    self._cam.exit()
                except Exception:
                    pass
                self._cam = None

    def _set_capture_target(self, card: bool) -> None:
        assert self._cam
        cfg = self._cam.get_config()
        try:
            widget = cfg.get_child_by_name("capturetarget")
        except gp.GPhoto2Error:
            return  # not every camera has one
        choices = [widget.get_choice(i) for i in range(widget.count_choices())]
        want = "card" if card else "ram"
        for choice in choices:
            if want in choice.lower():
                widget.set_value(choice)
                self._cam.set_config(cfg)
                return

    def info(self) -> dict[str, Any]:
        self.connect()
        with self._lock:
            assert self._cam
            try:
                model = self._cam.get_abilities().model
                out: dict[str, Any] = {"model": model}
                cfg = self._cam.get_config()
                for name in ("batterylevel", "imagequality", "shutterspeed", "f-number", "iso"):
                    try:
                        out[name] = cfg.get_child_by_name(name).get_value()
                    except gp.GPhoto2Error:
                        pass
                return out
            except gp.GPhoto2Error as e:
                raise CameraError(_explain(e)) from e

    def capture(self, dest_dir: Path, stem: str, context: dict[str, Any]) -> list[Path]:
        self.connect()
        try:
            return self._capture_once(dest_dir, stem)
        except CameraError:
            # A camera that dozed off or dropped off the bus often comes back
            # after reopening. Try once more before failing the scan.
            log.warning("capture failed, reconnecting and retrying once")
            self.close()
            self.connect()
            return self._capture_once(dest_dir, stem)

    def _capture_once(self, dest_dir: Path, stem: str) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            assert self._cam
            try:
                first = self._cam.capture(gp.GP_CAPTURE_IMAGE)
                files = [(first.folder, first.name)]
                # Collect any further files from the same shot.
                wait = int(self.options["extra_file_wait_ms"])
                deadline = time.monotonic() + wait / 1000 * 4
                while time.monotonic() < deadline:
                    ev, data = self._cam.wait_for_event(wait)
                    if ev == gp.GP_EVENT_FILE_ADDED:
                        files.append((data.folder, data.name))
                    elif ev == gp.GP_EVENT_TIMEOUT:
                        break
                saved = []
                for folder, name in files:
                    ext = PurePosixPath(name).suffix.lower() or ".jpg"
                    if ext == ".jpeg":
                        ext = ".jpg"
                    target = dest_dir / f"{stem}{ext}"
                    cf = self._cam.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL)
                    cf.save(str(target))
                    saved.append(target)
                    if not self.options["keep_on_card"]:
                        try:
                            self._cam.file_delete(folder, name)
                        except gp.GPhoto2Error:
                            pass  # files in the camera's RAM are gone already
                return saved
            except gp.GPhoto2Error as e:
                raise CameraError(_explain(e)) from e


register("gphoto2", GPhoto2Camera)
