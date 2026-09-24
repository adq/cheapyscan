# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey
"""Scan positions, generated the way OpenScan3 does it.

This is an independent implementation of the algorithm described in
OpenScan3's `utils/paths/paths.py` and `utils/paths/optimization.py`. No code
was copied; see the attribution section of the root README.

The points form a Fibonacci lattice on a band of the sphere. z = cos(theta) is
spaced evenly, so each point covers the same area of the band, and each step
turns the turntable by the golden-ratio fraction of the phi span.

Point i keeps its index for life. Photos are named by it, so reordering the
path for speed never changes which file holds which view.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

GOLDEN_RATIO_CONJUGATE = (math.sqrt(5) - 1) / 2


@dataclass(frozen=True)
class Point:
    index: int  # position in the Fibonacci sequence, used in file names
    theta: float  # rotor angle, degrees
    phi: float  # turntable angle, degrees

    def cartesian(self) -> tuple[float, float, float]:
        t, f = math.radians(self.theta), math.radians(self.phi)
        return (math.sin(t) * math.cos(f), math.sin(t) * math.sin(f), math.cos(t))


def phi_span(min_phi: float, max_phi: float) -> float:
    span = (max_phi - min_phi) % 360.0
    return span or 360.0


def fibonacci_path(
    n: int, min_theta: float, max_theta: float, min_phi: float = 0.0, max_phi: float = 360.0
) -> list[Point]:
    """n points from max_theta up to min_theta, in Fibonacci order."""
    if n < 1:
        raise ValueError("need at least one point")
    if min_theta > max_theta:
        raise ValueError("min_theta must not exceed max_theta")
    z_max = math.cos(math.radians(min_theta))
    z_min = math.cos(math.radians(max_theta))
    span = phi_span(min_phi, max_phi)
    points = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        z = z_min + (z_max - z_min) * frac
        theta = math.degrees(math.acos(max(-1.0, min(1.0, z))))
        theta = max(min_theta, min(max_theta, theta))
        phi = (min_phi + span * ((i * GOLDEN_RATIO_CONJUGATE) % 1.0)) % 360.0
        points.append(Point(i, theta, phi))
    return points


MoveCost = Callable[[float, float, float, float], float]


def nearest_neighbour(
    points: list[Point], start_theta: float, start_phi: float, cost: MoveCost
) -> list[Point]:
    """Greedy reorder: always go to the point that is quickest to reach.

    cost(theta_from, phi_from, theta_to, phi_to) returns the move time in
    seconds. Both axes move together, so a move takes as long as the slower
    axis. Ties go to the lower Fibonacci index, which keeps the result stable.
    """
    remaining = list(points)
    ordered: list[Point] = []
    theta, phi = start_theta, start_phi
    while remaining:
        best = min(
            range(len(remaining)),
            key=lambda k: (cost(theta, phi, remaining[k].theta, remaining[k].phi), remaining[k].index),
        )
        p = remaining.pop(best)
        ordered.append(p)
        theta, phi = p.theta, p.phi
    return ordered


def total_time(points: list[Point], start_theta: float, start_phi: float, cost: MoveCost) -> float:
    t = 0.0
    theta, phi = start_theta, start_phi
    for p in points:
        t += cost(theta, phi, p.theta, p.phi)
        theta, phi = p.theta, p.phi
    return t
