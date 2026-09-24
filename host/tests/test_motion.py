# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import pytest

from cheapyscan.config import Settings
from cheapyscan.motion import Axis


def axes():
    s = Settings()
    return Axis("rotor", s.rotor, wraps=False), Axis("turntable", s.turntable, wraps=True)


def test_reference_is_zero_steps():
    rot, tt = axes()
    assert rot.steps_to_angle(0) == 90
    assert tt.steps_to_angle(0) == 0
    assert rot.target_steps(0, 90) == 0


def test_round_trip():
    rot, _ = axes()
    for angle in (0, 12.5, 90, 125, 140):
        assert rot.steps_to_angle(rot.target_steps(0, angle)) == pytest.approx(angle, abs=360 / rot.cfg.steps_per_rev)


def test_turntable_takes_short_way_across_zero():
    _, tt = axes()
    at_350 = tt.target_steps(0, 350)
    assert at_350 == -round(10 * 3200 / 360)
    # From 350 to 10 is +20 degrees, not -340.
    assert tt.target_steps(at_350, 10) - at_350 == round(20 * 3200 / 360)


def test_turntable_wrapping_does_not_drift():
    _, tt = axes()
    steps = 0
    for _ in range(50):
        for angle in (137.5, 275.0, 52.5):
            steps = tt.target_steps(steps, angle)
    # The counter keeps growing as the turntable turns one way, but every
    # target is measured from the exact current count, so the angle stays on
    # the step grid.
    assert tt.steps_to_angle(steps) == pytest.approx(52.5, abs=360 / 3200)


def test_invert():
    s = Settings()
    s.rotor.invert = True
    rot = Axis("rotor", s.rotor, wraps=False)
    assert rot.target_steps(0, 100) < 0
    assert rot.steps_to_angle(rot.target_steps(0, 100)) == pytest.approx(100, abs=0.05)


def test_clamp():
    rot, tt = axes()
    assert rot.clamp(-5) == 0
    assert rot.clamp(200) == 140
    assert tt.clamp(370) == 10


async def test_move_on_simulator(rig):
    await rig.motion.set_reference()
    angles = await rig.motion.move_to(45, 200)
    assert angles["theta"] == pytest.approx(45, abs=0.05)
    assert angles["phi"] == pytest.approx(200, abs=0.2)
    angles = await rig.motion.move_by("turntable", 360)
    assert angles["phi"] == pytest.approx(200, abs=0.2)
