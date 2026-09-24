# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import asyncio
import json

import pytest

from cheapyscan.config import ScanSettings
from cheapyscan.rig import RigError


async def wait_state(rig, states, timeout=10):
    async def loop():
        while rig.scan.state not in states:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(loop(), timeout)


def small(points=12, settle_ms=0):
    return ScanSettings(points=points, settle_ms=settle_ms)


async def test_scan_needs_reference(rig):
    rig.projects.create("p")
    with pytest.raises(RigError, match="reference"):
        await rig.start_scan("p", small())


async def test_full_scan(rig):
    await rig.set_reference()
    rig.projects.create("vase")
    await rig.start_scan("vase", small())
    await rig.scan.wait()
    assert rig.scan.state == "completed"

    sdir = rig.projects.scan_dir("vase", 1)
    path = json.loads((sdir / "path.json").read_text())
    assert len(path) == 12
    assert sorted(e["original_step"] for e in path) == list(range(12))
    assert [e["execution_step"] for e in path] == list(range(12))

    record = json.loads((sdir / "scan.json").read_text())
    assert record["status"] == "completed"
    assert record["current_step"] == 12

    photos = rig.projects.photos("vase", 1)
    assert photos == [f"scan01_{i:03d}.jpg" for i in range(12)]
    meta = json.loads((sdir / "metadata" / "scan01_005.json").read_text())
    assert meta["step"] == 5
    assert meta["actual"]["theta"] == pytest.approx(meta["target"]["theta"], abs=0.05)
    assert (rig.projects.project_dir("vase") / "thumbnail.jpg").exists()

    # Returned to the end position.
    angles = rig.motion.angles()
    assert angles["theta"] == pytest.approx(90, abs=0.05)
    assert angles["phi"] == pytest.approx(0, abs=0.2)


async def test_second_scan_gets_next_index(rig):
    await rig.set_reference()
    rig.projects.create("p")
    for _ in range(2):
        await rig.start_scan("p", small(3))
        await rig.scan.wait()
    assert [s["index"] for s in rig.projects.scans("p")] == [1, 2]
    assert rig.projects.photos("p", 2)[0].startswith("scan02_")


async def test_pause_resume(rig):
    await rig.set_reference()
    rig.projects.create("p")
    await rig.start_scan("p", small(20, settle_ms=20))
    rig.scan.pause()
    await asyncio.sleep(0.2)
    step = rig.scan.current_step
    assert step < 20
    await asyncio.sleep(0.2)
    assert rig.scan.current_step == step
    with pytest.raises(RigError, match="under the scan"):
        await rig.move_by("rotor", 5)
    rig.scan.resume()
    await rig.scan.wait()
    assert rig.scan.state == "completed"


async def test_cancel_then_resume_from_disk(rig):
    await rig.set_reference()
    rig.projects.create("p")
    await rig.start_scan("p", small(20, settle_ms=20))
    while rig.scan.current_step < 3:
        await asyncio.sleep(0.01)
    rig.scan.cancel()
    await rig.scan.wait()
    assert rig.scan.state == "cancelled"
    done = rig.scan.current_step
    assert 3 <= done < 20
    assert len(rig.projects.photos("p", 1)) == done

    await rig.resume_scan("p", 1)
    await rig.scan.wait()
    assert rig.scan.state == "completed"
    assert len(rig.projects.photos("p", 1)) == 20


async def test_abort_fails_scan(rig):
    await rig.set_reference()
    rig.projects.create("p")
    rig.settings.rotor.rate = 10  # slow enough to abort mid move
    await rig.start_scan("p", small(5))
    while not (rig.scan.phase == "moving" and rig.motion.moving):
        await asyncio.sleep(0.001)
    await asyncio.sleep(0.01)
    await rig.fw.abort()
    await rig.scan.wait()
    assert rig.scan.state == "failed"
    assert "aborted" in rig.scan.error


async def test_rotor_range_checked(rig):
    await rig.set_reference()
    rig.projects.create("p")
    with pytest.raises(RigError, match="outside the rotor limits"):
        await rig.start_scan("p", ScanSettings(min_theta=0, max_theta=170))
