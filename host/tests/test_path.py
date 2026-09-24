# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

import math

import pytest

from cheapyscan.config import Settings
from cheapyscan.path import GOLDEN_RATIO_CONJUGATE, fibonacci_path, nearest_neighbour, total_time
from cheapyscan.rig import Rig


def test_count_and_limits():
    pts = fibonacci_path(130, 12, 125)
    assert len(pts) == 130
    assert [p.index for p in pts] == list(range(130))
    assert all(12 <= p.theta <= 125 for p in pts)
    assert all(0 <= p.phi < 360 for p in pts)


def test_starts_at_max_theta_and_climbs():
    pts = fibonacci_path(50, 20, 110)
    assert pts[0].theta == pytest.approx(110)
    assert pts[-1].theta == pytest.approx(20)
    assert all(a.theta >= b.theta for a, b in zip(pts, pts[1:]))


def test_even_spacing_in_z():
    pts = fibonacci_path(11, 30, 150)
    zs = [math.cos(math.radians(p.theta)) for p in pts]
    steps = [b - a for a, b in zip(zs, zs[1:])]
    assert all(s == pytest.approx(steps[0]) for s in steps)


def test_golden_angle_phi():
    pts = fibonacci_path(20, 12, 125)
    for p in pts:
        assert p.phi == pytest.approx(360 * ((p.index * GOLDEN_RATIO_CONJUGATE) % 1))


def test_phi_span_restricted():
    pts = fibonacci_path(40, 12, 125, 90, 180)
    assert all(90 <= p.phi <= 180 for p in pts)


def test_single_point():
    (p,) = fibonacci_path(1, 40, 80)
    assert p.theta == pytest.approx(80)


def test_nearest_neighbour_is_permutation_and_faster():
    rig = Rig(Settings())
    pts = fibonacci_path(130, 12, 125)
    nn = nearest_neighbour(pts, 90, 0, rig.move_cost)
    assert sorted(p.index for p in nn) == list(range(130))
    assert total_time(nn, 90, 0, rig.move_cost) < total_time(pts, 90, 0, rig.move_cost)
