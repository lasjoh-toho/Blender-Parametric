# SPDX-License-Identifier: GPL-3.0-or-later
"""Printability and stability checks.

``run(bm, profile)`` takes a bmesh in millimetres, standing the way it will be
printed (Z up), and returns a list of ``Check`` results with a traffic light
level. Nothing in here touches scene data, so it can be tested on its own.
"""

import math

import bpy  # noqa: F401  (must be imported before bmesh in the bpy module build)
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import convex_hull_2d

OK, WARN, FAIL = "OK", "WARN", "FAIL"

FDM = {
    "nozzle": 0.4, "layer_height": 0.2, "min_wall": 0.8, "min_detail": 0.4,
    "max_overhang": 45.0, "clearance": 0.2, "bed": (220.0, 220.0, 250.0),
}
RESIN = {
    "nozzle": 0.05, "layer_height": 0.05, "min_wall": 0.5, "min_detail": 0.2,
    "max_overhang": 30.0, "clearance": 0.1, "bed": (145.0, 80.0, 165.0),
}
PRESETS = {"FDM": FDM, "RESIN": RESIN}

# Slender parts wobble on the bed: height divided by the smallest width of the footprint.
SLENDER_WARN = 3.0
SLENDER_FAIL = 6.0
# How far the finished part can be tilted before it falls over (degrees).
TIP_WARN = 15.0
TIP_FAIL = 5.0


class Check:
    """One line of the report."""

    __slots__ = ("id", "label", "level", "text", "faces", "value")

    def __init__(self, id, label, level, text, faces=(), value=None):
        self.id = id
        self.label = label
        self.level = level
        self.text = text
        self.faces = list(faces)  # indices of the faces to highlight
        self.value = value

    def as_dict(self):
        return {"id": self.id, "label": self.label, "level": self.level, "text": self.text,
                "count": len(self.faces), "value": self.value}


def _num(value, digits=2):
    """German decimal comma, no trailing zeros."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text.replace(".", ",")


def worst(checks):
    levels = {c.level for c in checks}
    return FAIL if FAIL in levels else WARN if WARN in levels else OK


# ---------------------------------------------------------------------------
# single checks

def check_watertight(bm):
    edges = sum(1 for e in bm.edges if not e.is_manifold)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    if not bm.faces:
        return Check("watertight", "Wasserdicht", FAIL, "kein Körper vorhanden")
    if edges or loose:
        faces = {f.index for e in bm.edges if not e.is_manifold for f in e.link_faces}
        parts = []
        if edges:
            parts.append(f"{edges} offene Kanten")
        if loose:
            parts.append(f"{loose} lose Punkte")
        return Check("watertight", "Wasserdicht", FAIL, ", ".join(parts), sorted(faces), edges + loose)
    return Check("watertight", "Wasserdicht", OK, "geschlossen", value=0)


def check_normals(bm):
    try:
        volume = bm.calc_volume(signed=True)
    except Exception:
        volume = 0.0
    if volume < 0.0:
        return Check("normals", "Flächenrichtung", FAIL, "Flächen zeigen nach innen", value=volume)
    return Check("normals", "Flächenrichtung", OK, "außen", value=volume)


def bounds(bm):
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def check_build_volume(bm, profile):
    lo, hi = bounds(bm)
    size = tuple(h - l for l, h in zip(lo, hi))
    bed = tuple(profile["bed"])
    text = f"{_num(size[0], 1)} × {_num(size[1], 1)} × {_num(size[2], 1)} mm"
    fits = size[2] <= bed[2] + 1e-6 and (
        (size[0] <= bed[0] + 1e-6 and size[1] <= bed[1] + 1e-6)
        or (size[0] <= bed[1] + 1e-6 and size[1] <= bed[0] + 1e-6))
    if not fits:
        return Check("build_volume", "Bauraum", FAIL,
                     f"{text}, Bauraum {_num(bed[0], 0)} × {_num(bed[1], 0)} × {_num(bed[2], 0)} mm", value=size)
    return Check("build_volume", "Bauraum", OK, text, value=size)


def check_wall(bm, profile, tree=None):
    """Thickness at every face: a ray from its centre to the opposite side."""
    min_wall = profile["min_wall"]
    tree = tree or BVHTree.FromBMesh(bm)
    thin = []
    thinnest = None
    for face in bm.faces:
        normal = face.normal
        if normal.length_squared < 1e-12:
            continue
        origin = face.calc_center_median() - normal * 1e-4
        hit = tree.ray_cast(origin, -normal)
        if hit[0] is None:
            continue
        distance = hit[3] + 1e-4
        if thinnest is None or distance < thinnest:
            thinnest = distance
        if distance < min_wall - 1e-5:
            thin.append(face.index)
    if thinnest is None:
        return Check("wall", "Wandstärke", OK, "nicht messbar")
    if thin:
        return Check("wall", "Wandstärke", FAIL,
                     f"{_num(thinnest)} mm an {len(thin)} Flächen, Minimum {_num(min_wall)} mm", thin, thinnest)
    return Check("wall", "Wandstärke", OK, f"dünnste Stelle {_num(thinnest)} mm", value=thinnest)


def check_overhang(bm, profile):
    """Faces that look down more steeply than the profile allows; the bed carries the lowest ones."""
    limit = -math.sin(math.radians(profile["max_overhang"])) - 1e-4
    floor = bounds(bm)[0][2]
    tolerance = max(profile["layer_height"] * 0.5, 1e-3)
    faces = []
    area = 0.0
    for face in bm.faces:
        if face.normal.z >= limit:
            continue
        if all(v.co.z <= floor + tolerance for v in face.verts):
            continue
        faces.append(face.index)
        area += face.calc_area()
    if faces:
        return Check("overhang", "Überhang", WARN,
                     f"{_num(area, 1)} mm² über {_num(profile['max_overhang'], 0)}°, Stützen nötig", faces, area)
    return Check("overhang", "Überhang", OK, "ohne Stützen druckbar", value=0.0)


def centre_of_mass(bm):
    """Centre of the solid from signed tetrahedra; needs a closed mesh with triangles or fans."""
    total = 0.0
    centre = Vector((0.0, 0.0, 0.0))
    for face in bm.faces:
        verts = [v.co for v in face.verts]
        for i in range(1, len(verts) - 1):
            a, b, c = verts[0], verts[i], verts[i + 1]
            volume = a.dot(b.cross(c)) / 6.0
            total += volume
            centre += (a + b + c) * (volume / 4.0)
    if abs(total) < 1e-12:
        return None, 0.0
    return centre / total, total


def footprint(bm, tolerance):
    """Convex outline of everything that touches the bed, as a list of 2D points."""
    floor = bounds(bm)[0][2]
    points = [(v.co.x, v.co.y) for v in bm.verts if v.co.z <= floor + tolerance]
    if len(points) < 3:
        return points
    hull = convex_hull_2d(points)
    return [points[i] for i in hull]


def _edge_distances(hull, x, y):
    """Signed distance of (x, y) to every hull edge (positive inside) and the hull's smallest width."""
    n = len(hull)
    inside = []
    width = None
    orientation = sum(hull[i][0] * hull[(i + 1) % n][1] - hull[(i + 1) % n][0] * hull[i][1] for i in range(n))
    sign = 1.0 if orientation >= 0 else -1.0
    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey)
        if length < 1e-9:
            continue
        nx, ny = -ey / length * sign, ex / length * sign  # points to the inside
        inside.append((x - ax) * nx + (y - ay) * ny)
        span = max((px - ax) * nx + (py - ay) * ny for px, py in hull)
        width = span if width is None else min(width, span)
    return inside, width or 0.0


def check_stability(bm, profile):
    """Does the finished part stand, and is it too slender to print without wobbling?"""
    lo, hi = bounds(bm)
    height = hi[2] - lo[2]
    hull = footprint(bm, max(profile["layer_height"] * 0.5, 1e-3))
    centre, _volume = centre_of_mass(bm)
    if centre is None or len(hull) < 3:
        return [Check("stability", "Standfestigkeit", WARN, "keine ebene Auflage"),
                Check("slender", "Schlankheit", WARN, "keine ebene Auflage")]
    inside, width = _edge_distances(hull, centre.x, centre.y)
    margin = min(inside) if inside else 0.0
    rise = max(centre.z - lo[2], 1e-9)
    if margin <= 0.0:
        stand = Check("stability", "Standfestigkeit", FAIL, "Schwerpunkt liegt neben der Auflage, das Teil kippt",
                      value=0.0)
    else:
        angle = math.degrees(math.atan2(margin, rise))
        level = FAIL if angle < TIP_FAIL else WARN if angle < TIP_WARN else OK
        stand = Check("stability", "Standfestigkeit", level, f"kippt ab {_num(angle, 0)}° Neigung", value=angle)
    ratio = height / width if width > 1e-9 else float("inf")
    level = FAIL if ratio >= SLENDER_FAIL else WARN if ratio >= SLENDER_WARN else OK
    slender = Check("slender", "Schlankheit", level,
                    f"Höhe zu Auflage {_num(ratio, 1)} : 1" + (", wackelt beim Druck" if level != OK else ""),
                    value=ratio)
    return [stand, slender]


# ---------------------------------------------------------------------------

def run(bm, profile):
    """All checks for a bmesh in millimetres. Returns a list of ``Check``."""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    bm.normal_update()
    first = check_watertight(bm)
    if not bm.faces:
        return [first]
    checks = [first, check_normals(bm), check_build_volume(bm, profile)]
    closed = first.level == OK
    if closed:
        checks.append(check_wall(bm, profile))
    else:
        checks.append(Check("wall", "Wandstärke", WARN, "erst messbar, wenn der Körper geschlossen ist"))
    checks.append(check_overhang(bm, profile))
    if closed:
        checks.extend(check_stability(bm, profile))
    return checks
