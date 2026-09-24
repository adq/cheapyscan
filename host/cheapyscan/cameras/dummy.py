# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""A camera that draws the scan position into a generated JPEG.

Used with `--simulate` and in the tests, so a whole scan runs with no camera.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .base import Camera, register


class DummyCamera(Camera):
    description = "Generated test images. No camera needed."
    default_options = {"width": 960, "height": 640, "delay_ms": 200}

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def info(self) -> dict[str, Any]:
        return {"model": "Dummy camera"}

    def capture(self, dest_dir: Path, stem: str, context: dict[str, Any]) -> list[Path]:
        time.sleep(self.options["delay_ms"] / 1000)
        w, h = int(self.options["width"]), int(self.options["height"])
        theta = float(context.get("theta", 0.0))
        phi = float(context.get("phi", 0.0))
        # Colour follows the position, so different views look different.
        bg = (int(40 + theta), int(40 + phi / 2) % 256, 120)
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        lines = [stem, f"theta {theta:.1f}", f"phi {phi:.1f}"]
        d.multiline_text((24, 24), "\n".join(lines), fill=(255, 255, 255), font_size=48)
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{stem}.jpg"
        img.save(path, quality=85)
        return [path]


register("dummy", DummyCamera)
