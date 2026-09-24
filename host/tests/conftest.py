# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import pytest

from cheapyscan.config import Settings
from cheapyscan.rig import Rig


@pytest.fixture
def settings(tmp_path):
    s = Settings(projects_dir=str(tmp_path / "projects"))
    s.camera.backend = "dummy"
    s.camera.options = {"delay_ms": 0, "width": 320, "height": 240}
    return s


@pytest.fixture
async def rig(settings):
    # Moves run at 1/1000 of real time, so a scan takes a fraction of a second.
    r = Rig(settings, simulate=True, sim_time_scale=0.001)
    await r.connect()
    r.camera = None
    yield r
    await r.shutdown()
