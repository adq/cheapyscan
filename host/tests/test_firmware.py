# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import asyncio

import pytest

from cheapyscan.firmware import FirmwareClient, FirmwareError, parse_status
from cheapyscan.simulator import SimulatedTransport


@pytest.fixture
async def fw():
    t = SimulatedTransport(time_scale=0.01, boot_delay=0.01)
    c = FirmwareClient(t)
    await c.connect()
    yield c
    c.close()


def test_parse_status():
    s = parse_status("pos X=-12 Y=300 busy X=0 Y=1 hold X=1 Y=0")
    assert s.pos == {"X": -12, "Y": 300}
    assert s.busy == {"X": False, "Y": True}
    assert s.hold == {"X": True, "Y": False}


async def test_move_and_done(fw):
    done = await fw.move("X", 400, 4000)
    await asyncio.wait_for(done, 2)
    s = await fw.status()
    assert s.pos["X"] == 400 and not s.busy["X"]


async def test_both_axes_together(fw):
    a = await fw.move("X", -200, 2000)
    b = await fw.move("Y", 300, 2000)
    await asyncio.wait_for(asyncio.gather(a, b), 2)
    s = await fw.status()
    assert s.pos == {"X": -200, "Y": 300}


async def test_busy_is_an_error(fw):
    await fw.move("X", 4000, 100)
    with pytest.raises(FirmwareError, match="err busy"):
        await fw.move("X", 10, 100)


async def test_abort_still_sends_done(fw):
    done = await fw.move("Y", 4000, 100)
    await fw.abort()
    await asyncio.wait_for(done, 2)
    s = await fw.status()
    assert 0 <= s.pos["Y"] < 4000


async def test_zero_step_move_is_complete(fw):
    done = await fw.move("X", 0, 400)
    assert done.done()


async def test_hold_and_zero(fw):
    await fw.hold("X", False)
    await asyncio.wait_for(await fw.move("X", 50, 4000), 2)
    await fw.zero("X")
    s = await fw.status()
    assert s.pos["X"] == 0 and s.hold["X"] is False


async def test_overlong_command_refused(fw):
    with pytest.raises(FirmwareError, match="too long"):
        await fw._command("M X " + "1" * 60)


async def test_no_banner_times_out():
    t = SimulatedTransport(boot_delay=10)
    c = FirmwareClient(t)
    with pytest.raises(FirmwareError, match="ready banner"):
        await c.connect(banner_timeout=0.1)
