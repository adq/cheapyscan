# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Camera backends. Import this package to register the built-in ones."""

from .base import Camera, CameraError, available, create, register
from . import dummy as _dummy  # noqa: F401  (registers "dummy")
from . import gphoto2_camera as _gphoto2  # noqa: F401  (registers "gphoto2")

__all__ = ["Camera", "CameraError", "available", "create", "register"]
