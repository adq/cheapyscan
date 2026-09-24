# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""What a camera backend must provide.

A backend is one class that subclasses `Camera`, plus a `register()` call.
The scan asks it for one thing, `capture()`, which writes the photo into the
scan folder under the name it is given and returns the paths it wrote. A
camera set to RAW + JPEG returns two paths for one shot.

Backends are synchronous. The scan runs them in a worker thread, so a slow
USB transfer never stalls the web server.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any


class CameraError(Exception):
    pass


class Camera(abc.ABC):
    #: Shown on the Settings page.
    description: str = ""
    #: Option names and defaults, shown on the Settings page.
    default_options: dict[str, Any] = {}

    def __init__(self, options: dict[str, Any]):
        self.options = {**self.default_options, **options}

    @abc.abstractmethod
    def connect(self) -> None:
        """Open the camera. Raise CameraError with a how-to-fix message."""

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def info(self) -> dict[str, Any]:
        """Model name and anything else worth showing, as plain values."""

    @abc.abstractmethod
    def capture(self, dest_dir: Path, stem: str, context: dict[str, Any]) -> list[Path]:
        """Take one photo and save it as dest_dir/stem.<ext>.

        context carries the scan position for backends that want it, such as
        the dummy camera, which draws it into the image.
        """


_REGISTRY: dict[str, type[Camera]] = {}


def register(name: str, cls: type[Camera]) -> None:
    _REGISTRY[name] = cls


def available() -> dict[str, dict[str, Any]]:
    return {
        name: {"description": cls.description, "default_options": cls.default_options}
        for name, cls in _REGISTRY.items()
    }


def create(name: str, options: dict[str, Any]) -> Camera:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise CameraError(f"No camera backend called {name!r}. Known: {', '.join(_REGISTRY)}")
    return cls(options)
