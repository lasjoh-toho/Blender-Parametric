# SPDX-License-Identifier: GPL-3.0-or-later
"""2D geometric constraint solver for sketches (Levenberg-Marquardt, numpy only).

The solver knows nothing about Blender. A sketch is described with plain data:

    points   list of [x, y]
    fixed    set of point indices that must not move
    circles  list of (centre point index, radius)
    arcs     list of (centre, start, end) point indices
    constraints  list of Constraint

Unknowns are the coordinates of all free points and the circle radii. Every
constraint contributes one or more residuals that are zero when it holds.
"""

import math

import numpy as np

TOLERANCE = 1e-6

# kind -> (number of point references, needs curve, has value)
KINDS = {
    "COINCIDENT": (2, False, False),
    "HORIZONTAL": (2, False, False),
    "VERTICAL": (2, False, False),
    "DISTANCE": (2, False, True),
    "PARALLEL": (4, False, False),
    "PERPENDICULAR": (4, False, False),
    "EQUAL": (4, False, False),
    "ANGLE": (4, False, True),
    "POINT_ON_LINE": (3, False, False),
    "MIDPOINT": (3, False, False),
    "RADIUS": (0, True, True),
    "TANGENT": (2, True, False),
    "POINT_ON_CURVE": (1, True, False),
}


class Constraint:
    __slots__ = ("kind", "points", "curve", "value")

    def __init__(self, kind, points=(), curve=None, value=0.0):
        if kind not in KINDS:
            raise ValueError(f"unknown constraint {kind}")
        self.kind = kind
        self.points = tuple(points)
        self.curve = curve  # ("CIRCLE", index) or ("ARC", index)
        self.value = float(value)


class Result:
    def __init__(self, points, radii, residual, dof, converged, iterations):
        self.points = points
        self.radii = radii
        self.residual = residual
        self.dof = dof
        self.converged = converged
        self.iterations = iterations

    @property
    def status(self):
        if not self.converged:
            return "CONFLICT"
        if self.dof == 0:
            return "FULL"
        return "UNDER"


def _wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


class _Problem:
    def __init__(self, points, fixed, circles, arcs, constraints, drag):
        self.p0 = np.array(points, dtype=float).reshape(-1, 2)
        self.circles = list(circles)
        self.arcs = list(arcs)
        self.constraints = list(constraints)
        self.drag = drag or {}
        n = len(self.p0)
        self.free = [i for i in range(n) if i not in fixed]
        self.col = {i: 2 * k for k, i in enumerate(self.free)}
        self.nr_point_vars = 2 * len(self.free)
        self.r0 = np.array([c[1] for c in self.circles], dtype=float)
        self.x0 = np.concatenate([self.p0[self.free].ravel(), self.r0]) if n or len(self.r0) else np.zeros(0)
        # Scale residuals of lengths by the sketch size so tolerances are relative.
        if n:
            span = float(np.max(self.p0.max(axis=0) - self.p0.min(axis=0)))
        else:
            span = 0.0
        self.scale = max(span, float(self.r0.max()) if len(self.r0) else 0.0, 1.0)

    def unpack(self, x):
        pts = self.p0.copy()
        if self.free:
            pts[self.free] = x[: self.nr_point_vars].reshape(-1, 2)
        return pts, x[self.nr_point_vars:]

    def curve_radius(self, curve, pts, radii):
        kind, index = curve
        if kind == "CIRCLE":
            return self.circles[index][0], radii[index]
        c, s, _e = self.arcs[index]
        return c, float(np.hypot(*(pts[s] - pts[c])))

    def residuals(self, x, with_drag=True):
        pts, radii = self.unpack(x)
        s = self.scale
        out = []
        for c, a, e in self.arcs:
            out.append((np.hypot(*(pts[a] - pts[c])) - np.hypot(*(pts[e] - pts[c]))) / s)
        for con in self.constraints:
            k = con.kind
            p = [pts[i] for i in con.points]
            if k == "COINCIDENT":
                out.extend((p[0] - p[1]) / s)
            elif k == "HORIZONTAL":
                out.append((p[0][1] - p[1][1]) / s)
            elif k == "VERTICAL":
                out.append((p[0][0] - p[1][0]) / s)
            elif k == "DISTANCE":
                out.append((np.hypot(*(p[0] - p[1])) - con.value) / s)
            elif k in {"PARALLEL", "PERPENDICULAR", "ANGLE", "EQUAL"}:
                d1 = p[1] - p[0]
                d2 = p[3] - p[2]
                l1 = np.hypot(*d1)
                l2 = np.hypot(*d2)
                if k == "EQUAL":
                    out.append((l1 - l2) / s)
                    continue
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                dot = d1[0] * d2[0] + d1[1] * d2[1]
                norm = max(l1 * l2, 1e-12)
                if k == "PARALLEL":
                    out.append(cross / norm)
                elif k == "PERPENDICULAR":
                    out.append(dot / norm)
                else:
                    out.append(_wrap(math.atan2(cross, dot) - con.value))
            elif k == "POINT_ON_LINE":
                d = p[2] - p[1]
                v = p[0] - p[1]
                out.append((v[0] * d[1] - v[1] * d[0]) / max(np.hypot(*d), 1e-12) / s)
            elif k == "MIDPOINT":
                out.extend((p[0] - (p[1] + p[2]) / 2) / s)
            elif k == "RADIUS":
                _c, r = self.curve_radius(con.curve, pts, radii)
                out.append((r - con.value) / s)
            elif k == "TANGENT":
                c, r = self.curve_radius(con.curve, pts, radii)
                d = p[1] - p[0]
                v = pts[c] - p[0]
                dist = abs(v[0] * d[1] - v[1] * d[0]) / max(np.hypot(*d), 1e-12)
                out.append((dist - r) / s)
            elif k == "POINT_ON_CURVE":
                c, r = self.curve_radius(con.curve, pts, radii)
                out.append((np.hypot(*(p[0] - pts[c])) - r) / s)
        # radii must stay positive
        for r in radii:
            out.append(min(r, 0.0) / s)
        hard = len(out)
        if with_drag:
            for index, (tx, ty) in self.drag.items():
                if index in self.col:
                    out.extend(0.05 * (pts[index] - np.array((tx, ty))) / s)
        return np.array(out, dtype=float), hard

    def jacobian(self, x, r0=None, with_drag=True):
        if r0 is None:
            r0, _ = self.residuals(x, with_drag)
        jac = np.zeros((len(r0), len(x)))
        step = 1e-6 * self.scale
        for j in range(len(x)):
            xj = x.copy()
            xj[j] += step
            rj, _ = self.residuals(xj, with_drag)
            jac[:, j] = (rj - r0) / step
        return jac


def solve(points, constraints, fixed=(), circles=(), arcs=(), drag=None, max_iterations=80):
    """Solve the sketch. ``drag`` maps point index -> (x, y) the user pulls it towards.

    Returns a Result. Points move as little as possible from where they are.
    """
    prob = _Problem(points, set(fixed), circles, arcs, constraints, drag)
    x = prob.x0.copy()
    if len(x) == 0:
        r, hard = prob.residuals(x)
        err = float(np.max(np.abs(r[:hard]))) if hard else 0.0
        return Result(prob.p0, prob.r0, err, 0, err < TOLERANCE * 10, 0)

    lam = 1e-3
    r, hard = prob.residuals(x)
    cost = float(r @ r)
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        if hard == 0 and not prob.drag:
            break
        jac = prob.jacobian(x, r)
        grad = jac.T @ r
        hess = jac.T @ jac
        improved = False
        for _ in range(12):
            try:
                delta = np.linalg.solve(hess + lam * (np.diag(np.diag(hess)) + 1e-9 * np.eye(len(x))), -grad)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            x_new = x + delta
            r_new, _ = prob.residuals(x_new)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                x, r, cost = x_new, r_new, cost_new
                lam = max(lam / 5, 1e-9)
                improved = True
                break
            lam *= 5
        hard_err = float(np.max(np.abs(r[:hard]))) if hard else 0.0
        if not improved or (hard_err < TOLERANCE * 0.01 and not prob.drag) or float(np.max(np.abs(delta))) < 1e-10 * prob.scale:
            break

    pts, radii = prob.unpack(x)
    if prob.drag:
        # Second pass without the pull: lands exactly on the constraints, close to where the drag led.
        moved_circles = [(c[0], float(radii[i])) for i, c in enumerate(prob.circles)]
        return solve(pts, constraints, fixed, moved_circles, arcs, None, max_iterations)
    r_hard, hard = prob.residuals(x, with_drag=False)
    err = float(np.max(np.abs(r_hard))) if len(r_hard) else 0.0
    converged = err < TOLERANCE * 10
    # Degrees of freedom: unknowns minus independent constraints.
    if len(r_hard):
        jac = prob.jacobian(x, r_hard, with_drag=False)
        rank = int(np.linalg.matrix_rank(jac, tol=1e-7))
    else:
        rank = 0
    dof = len(x) - rank
    return Result(pts, radii, err * prob.scale, dof, converged, iterations)
