# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Settings for the host application, stored as one JSON file.

Everything the firmware does not know lives here: which firmware axis is
which, how many steps make a revolution, the angle limits, the camera backend
and where projects are saved. It can all change from the Settings page without
reflashing the board.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cheapyscan" / "config.json"


class AxisSettings(BaseModel):
    """One motor, as the host sees it.

    The firmware counts steps from zero at power-on or at the last `Z`. The
    host treats a count of zero as `reference_angle`, so setting the reference
    means putting the axis at that angle by hand and zeroing the counter.
    """

    firmware_axis: Literal["X", "Y"]
    steps_per_rev: float = Field(gt=0)
    invert: bool = False
    min_angle: float
    max_angle: float
    rate: int = Field(ge=10, le=4000, description="steps per second")
    reference_angle: float


class ScanSettings(BaseModel):
    """One scan. Defaults match OpenScan3's `ScanSetting`, except settle_ms.

    OpenScan3 defaults to no pause before capture. On the Classic the object
    itself tilts, so a short pause lets it stop swaying before the shutter.
    """

    points: int = Field(default=130, ge=1, le=999)
    min_theta: float = Field(default=12.0, ge=0, le=180)
    max_theta: float = Field(default=125.0, ge=0, le=180)
    min_phi: float = Field(default=0.0, ge=0, le=360)
    max_phi: float = Field(default=360.0, ge=0, le=360)
    optimize_path: bool = True
    settle_ms: int = Field(default=500, ge=0, le=60000)


class CameraSettings(BaseModel):
    backend: str = "gphoto2"
    options: dict[str, Any] = Field(default_factory=dict)


class EndPosition(BaseModel):
    theta: float = 90.0
    phi: float = 0.0


class Settings(BaseModel):
    serial_port: str | None = Field(
        default=None, description="None means find the board automatically"
    )
    rotor: AxisSettings = AxisSettings(
        firmware_axis="Y",
        # 64:12 gear on a 200 step motor at 1/16 microstepping.
        steps_per_rev=3200 * 64 / 12,
        min_angle=0.0,
        max_angle=140.0,
        rate=1200,
        reference_angle=90.0,
    )
    turntable: AxisSettings = AxisSettings(
        firmware_axis="X",
        steps_per_rev=3200,
        min_angle=0.0,
        max_angle=360.0,
        rate=800,
        reference_angle=0.0,
    )
    camera: CameraSettings = CameraSettings()
    projects_dir: str = str(Path.home() / "cheapyscan-projects")
    end_position: EndPosition = EndPosition()
    scan_defaults: ScanSettings = ScanSettings()


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    return Settings.model_validate_json(path.read_text())


def save(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings.model_dump(), indent=2) + "\n")
    tmp.replace(path)
