# SPDX-License-Identifier: GPL-3.0-or-later
"""bmesh building blocks used by the nodes.

Every function returns a *new* ``bmesh.types.BMesh`` or modifies the one it
gets in place and returns it. Primitives sit centred on the XY origin with
their base on Z = 0, which is the natural position for 3D printing.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

EPS = 1e-6


class GeometryError(ValueError):
    pass


# ---------------------------------------------------------------------------
# helpers

def new():
    return bmesh.new()


def copy(bm):
    return bm.copy() if bm is not None else bmesh.new()


def finish(bm, merge=False):
    """Clean up after an operation: optional vertex merge and consistent normals."""
    if merge and bm.verts:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return bm


def join(target, other):
    """Append ``other`` to ``target`` (both bmeshes). ``other`` is left untouched."""
    if other is None or not other.verts:
        return target
    me = bpy.data.meshes.new("_param_join")
    try:
        other.to_mesh(me)
        target.from_mesh(me)
    finally:
        bpy.data.meshes.remove(me)
    return target


def transform(bm, matrix):
    if bm.verts:
        bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts[:])
    return bm


def compose(translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1)):
    """Matrix from translation, Euler rotation (radians, XYZ) and scale."""
    from mathutils import Euler
    loc = Matrix.Translation(Vector(translation))
    rot = Euler(rotation, "XYZ").to_matrix().to_4x4()
    sca = Matrix.Diagonal(Vector((scale[0], scale[1], scale[2], 1.0)))
    return loc @ rot @ sca


def is_flat_profile(bm):
    return bool(bm.verts) and all(abs(v.co.z - bm.verts[0].co.z) < 1e-5 for v in bm.verts) and bool(bm.faces)


def stats(bm):
    """Return a dict with numbers that matter for 3D printing."""
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    try:
        volume = abs(bm.calc_volume(signed=False))
    except Exception:
        volume = 0.0
    if bm.verts:
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    else:
        dims = (0.0, 0.0, 0.0)
    islands = _count_islands(bm)
    return {
        "verts": len(bm.verts),
        "faces": len(bm.faces),
        "non_manifold_edges": non_manifold,
        "loose_verts": loose,
        "volume": volume,
        "dimensions": dims,
        "islands": islands,
    }


def _count_islands(bm):
    bm.verts.index_update()
    seen = set()
    count = 0
    for start in bm.verts:
        if start.index in seen:
            continue
        count += 1
        stack = [start]
        while stack:
            v = stack.pop()
            if v.index in seen:
                continue
            seen.add(v.index)
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in seen:
                    stack.append(o)
    return count


# ---------------------------------------------------------------------------
# primitives

def box(width, depth, height):
    width, depth, height = _positive(width, "Breite"), _positive(depth, "Tiefe"), _positive(height, "Höhe")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    transform(bm, Matrix.Translation((0, 0, height / 2)) @ Matrix.Diagonal((width, depth, height, 1)))
    return finish(bm)


def cylinder(radius, height, segments):
    return cone(radius, radius, height, segments)


def cone(radius_bottom, radius_top, height, segments):
    height = _positive(height, "Höhe")
    radius_bottom = max(0.0, radius_bottom)
    radius_top = max(0.0, radius_top)
    if radius_bottom < EPS and radius_top < EPS:
        raise GeometryError("Mindestens ein Radius muss größer als 0 sein")
    segments = max(3, int(segments))
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=height,
    )
    transform(bm, Matrix.Translation((0, 0, height / 2)))
    return finish(bm, merge=radius_top < EPS or radius_bottom < EPS)


def sphere(radius, segments, rings):
    radius = _positive(radius, "Radius")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=max(3, int(segments)), v_segments=max(3, int(rings)), radius=radius)
    transform(bm, Matrix.Translation((0, 0, radius)))
    return finish(bm)


# ---------------------------------------------------------------------------
# 2D profiles (single face in the XY plane, counter-clockwise)

def profile_from_points(points):
    pts = []
    for p in points:
        if not pts or (Vector(p) - Vector(pts[-1])).length > EPS:
            pts.append((float(p[0]), float(p[1])))
    if len(pts) > 2 and (Vector(pts[0]) - Vector(pts[-1])).length < EPS:
        pts.pop()
    if len(pts) < 3:
        raise GeometryError("Ein Profil braucht mindestens 3 verschiedene Punkte")
    # Make sure the outline runs counter-clockwise so the face normal points up.
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if abs(area) < EPS:
        raise GeometryError("Das Profil hat keine Fläche")
    if area < 0:
        pts.reverse()
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, 0.0)) for x, y in pts]
    try:
        bm.faces.new(verts)
    except ValueError:
        raise GeometryError("Das Profil überschneidet sich selbst")
    return finish(bm)


def rectangle_points(width, height, corner_radius=0.0, corner_segments=8):
    w = _positive(width, "Breite") / 2
    h = _positive(height, "Höhe") / 2
    r = max(0.0, min(corner_radius, w, h))
    if r < EPS:
        return [(-w, -h), (w, -h), (w, h), (-w, h)]
    pts = []
    corners = [((w - r, -h + r), -90), ((w - r, h - r), 0), ((-w + r, h - r), 90), ((-w + r, -h + r), 180)]
    for (cx, cy), start in corners:
        for i in range(corner_segments + 1):
            a = math.radians(start + 90 * i / corner_segments)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle_points(radius, segments):
    radius = _positive(radius, "Radius")
    segments = max(3, int(segments))
    return [(radius * math.cos(2 * math.pi * i / segments), radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]


def polygon_points(radius, sides):
    radius = _positive(radius, "Radius")
    sides = max(3, int(sides))
    offset = math.pi / 2  # first corner points up (+Y)
    return [(radius * math.cos(offset + 2 * math.pi * i / sides), radius * math.sin(offset + 2 * math.pi * i / sides)) for i in range(sides)]


# ---------------------------------------------------------------------------
# operations

def extrude(bm, height, direction=(0.0, 0.0, 1.0)):
    """Extrude every face of a flat profile along ``direction`` by ``height``."""
    if not bm.verts:
        return bm  # empty profile (e.g. a sketch without a closed outline yet)
    if not bm.faces:
        raise GeometryError("Extrudieren braucht ein Profil mit Fläche")
    if abs(height) < EPS:
        raise GeometryError("Die Höhe darf nicht 0 sein")
    d = Vector(direction)
    if d.length < EPS:
        d = Vector((0, 0, 1))
    d = d.normalized() * height
    faces = bm.faces[:]
    ret = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=d, verts=new_verts)
    return finish(bm)


def revolve(bm, angle, segments, offset=0.0):
    """Revolve a flat XY profile around the Z axis.

    The profile is first turned upright (profile X = distance from the axis,
    profile Y = height) and moved ``offset`` away from the axis.
    """
    if not bm.verts:
        return bm
    if not bm.faces:
        raise GeometryError("Rotieren braucht ein Profil mit Fläche")
    segments = max(3, int(segments))
    upright = Matrix.Translation((offset, 0, 0)) @ Matrix.Rotation(math.radians(90), 4, "X")
    transform(bm, upright)
    xs = [v.co.x for v in bm.verts]
    if min(xs) < -EPS and max(xs) > EPS:
        raise GeometryError("Das Profil kreuzt die Drehachse, vergrößere den Achsabstand")
    full = abs(abs(angle) - 2 * math.pi) < 1e-4 or abs(angle) > 2 * math.pi
    if abs(angle) < 1e-4:
        raise GeometryError("Der Winkel darf nicht 0 sein")
    if full:
        boundary = [e for e in bm.edges if e.is_boundary]
        verts = list({v for e in boundary for v in e.verts})
        for f in bm.faces[:]:
            bm.faces.remove(f)
        bmesh.ops.spin(
            bm,
            geom=verts + boundary,
            cent=(0, 0, 0),
            axis=(0, 0, 1),
            angle=2 * math.pi,
            steps=segments,
            use_merge=True,
            use_duplicate=False,
        )
        return _clean_revolved(bm)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.spin(
        bm,
        geom=geom,
        cent=(0, 0, 0),
        axis=(0, 0, 1),
        angle=angle,
        steps=segments,
        use_merge=False,
        use_duplicate=False,
    )
    return _clean_revolved(bm)


def _clean_revolved(bm):
    """Merge the seam and the points that lie on the axis, drop collapsed faces."""
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges[:])
    loose = [e for e in bm.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="EDGES")
    lonely = [v for v in bm.verts if not v.link_edges]
    if lonely:
        bmesh.ops.delete(bm, geom=lonely, context="VERTS")
    return finish(bm)


def bevel(bm, width, segments, angle_limit):
    """Bevel all edges whose face angle is at least ``angle_limit`` (radians)."""
    if width < EPS:
        return bm
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) >= angle_limit - 1e-6]
    if not edges:
        return bm
    bmesh.ops.bevel(
        bm,
        geom=edges,
        offset=width,
        offset_type="OFFSET",
        profile_type="SUPERELLIPSE",
        segments=max(1, int(segments)),
        profile=0.5,
        affect="EDGES",
        clamp_overlap=True,
    )
    return finish(bm)


def mirror(bm, axis, merge, keep_original=True):
    axis_index = {"X": 0, "Y": 1, "Z": 2}[axis]
    scale = [1.0, 1.0, 1.0]
    scale[axis_index] = -1.0
    m = Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    if not keep_original:
        transform(bm, m)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        return finish(bm)
    mirrored = bm.copy()
    transform(mirrored, m)
    bmesh.ops.reverse_faces(mirrored, faces=mirrored.faces[:])
    join(bm, mirrored)
    mirrored.free()
    return finish(bm, merge=merge)


def linear_array(bm, count, offset):
    count = max(1, int(count))
    if count > 1000:
        raise GeometryError("Höchstens 1000 Kopien")
    original = bm.copy()
    off = Vector(offset)
    for i in range(1, count):
        part = original.copy()
        transform(part, Matrix.Translation(off * i))
        join(bm, part)
        part.free()
    original.free()
    return finish(bm)


def radial_array(bm, count, axis, total_angle, center=(0.0, 0.0, 0.0)):
    count = max(1, int(count))
    if count > 1000:
        raise GeometryError("Höchstens 1000 Kopien")
    full = abs(abs(total_angle) - 2 * math.pi) < 1e-4
    step = total_angle / count if full else (total_angle / (count - 1) if count > 1 else 0.0)
    c = Vector(center)
    original = bm.copy()
    for i in range(1, count):
        part = original.copy()
        m = Matrix.Translation(c) @ Matrix.Rotation(step * i, 4, axis) @ Matrix.Translation(-c)
        transform(part, m)
        join(bm, part)
        part.free()
    original.free()
    return finish(bm)


# ---------------------------------------------------------------------------

def _positive(value, label):
    if value <= EPS:
        raise GeometryError(f"{label} muss größer als 0 sein")
    return float(value)
