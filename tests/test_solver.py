# SPDX-License-Identifier: GPL-3.0-or-later
"""Solver tests that need only numpy: python tests/test_solver.py"""

import importlib.util
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sketch_solver", os.path.join(ROOT, "parametric_design", "core", "sketch_solver.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)
C = ss.Constraint


def close(a, b, tol=1e-4):
    assert abs(a - b) < tol, (a, b)


def test_rectangle_fully_defined():
    pts = [[0, 0], [9, 1], [11, 6], [-1, 5]]
    cons = [C("HORIZONTAL", (0, 1)), C("VERTICAL", (1, 2)), C("HORIZONTAL", (2, 3)), C("VERTICAL", (3, 0)),
            C("DISTANCE", (0, 1), value=30), C("DISTANCE", (1, 2), value=20)]
    res = ss.solve(pts, cons, fixed={0})
    assert res.status == "FULL", (res.status, res.dof, res.residual)
    close(res.points[2][0], 30)
    close(res.points[2][1], 20)
    close(res.points[3][0], 0)


def test_under_defined_counts_dof():
    pts = [[0, 0], [9, 1], [11, 6], [-1, 5]]
    cons = [C("HORIZONTAL", (0, 1)), C("VERTICAL", (1, 2)), C("HORIZONTAL", (2, 3)), C("VERTICAL", (3, 0))]
    res = ss.solve(pts, cons, fixed={0})
    assert res.status == "UNDER" and res.dof == 2, (res.status, res.dof)


def test_conflict_detected():
    pts = [[0, 0], [10, 0]]
    cons = [C("DISTANCE", (0, 1), value=10), C("DISTANCE", (0, 1), value=20)]
    res = ss.solve(pts, cons, fixed={0})
    assert res.status == "CONFLICT", res.status


def test_angle_parallel_perpendicular_equal():
    pts = [[0, 0], [10, 0], [0, 0.5], [7, 6], [20, 0], [21, 9]]
    cons = [C("HORIZONTAL", (0, 1)), C("DISTANCE", (0, 1), value=10),
            C("COINCIDENT", (0, 2)), C("ANGLE", (0, 1, 2, 3), value=math.radians(60)), C("EQUAL", (0, 1, 2, 3)),
            C("PERPENDICULAR", (0, 1, 4, 5))]
    res = ss.solve(pts, cons, fixed={0})
    assert res.converged, res.residual
    close(res.points[3][0], 5)
    close(res.points[3][1], 10 * math.sin(math.radians(60)))
    close(res.points[4][0], res.points[5][0])


def test_circle_tangent_and_radius():
    pts = [[0, 0], [20, 0], [10, 7]]
    cons = [C("HORIZONTAL", (0, 1)), C("RADIUS", curve=("CIRCLE", 0), value=5), C("TANGENT", (0, 1), curve=("CIRCLE", 0))]
    res = ss.solve(pts, cons, fixed={0, 1}, circles=[(2, 3.0)])
    assert res.converged
    close(res.radii[0], 5)
    close(abs(res.points[2][1]), 5)


def test_arc_keeps_radius_and_point_on_curve():
    pts = [[0, 0], [10, 0], [1, 9], [6, 6]]
    cons = [C("POINT_ON_CURVE", (3,), curve=("ARC", 0)), C("RADIUS", curve=("ARC", 0), value=10)]
    res = ss.solve(pts, cons, fixed={0}, arcs=[(0, 1, 2)])
    assert res.converged
    for i in (1, 2, 3):
        close(math.hypot(*res.points[i]), 10)


def test_midpoint_and_point_on_line():
    pts = [[0, 0], [10, 10], [3, 6], [8, 1]]
    cons = [C("MIDPOINT", (2, 0, 1)), C("POINT_ON_LINE", (3, 0, 1))]
    res = ss.solve(pts, cons, fixed={0, 1})
    close(res.points[2][0], 5)
    close(res.points[2][1], 5)
    close(res.points[3][0], res.points[3][1])


def test_drag_respects_constraints():
    pts = [[0, 0], [10, 0]]
    cons = [C("DISTANCE", (0, 1), value=10)]
    res = ss.solve(pts, cons, fixed={0}, drag={1: (0, 30)})
    assert res.converged
    close(math.hypot(*res.points[1]), 10)
    assert res.points[1][1] > 9.5, res.points[1]


def test_minimal_movement_without_constraints():
    pts = [[1, 2], [3, 4]]
    res = ss.solve(pts, [])
    assert res.status == "UNDER" and res.dof == 4
    close(res.points[1][0], 3)


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print("ok   ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL ", t.__name__, repr(exc))
    print(f"{len(tests) - failed}/{len(tests)} solver tests passed")
    sys.exit(1 if failed else 0)
