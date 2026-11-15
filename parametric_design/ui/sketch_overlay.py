# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws the sketch of the active object in the viewport: lines, points, dimensions, rubber band."""

import math

import blf
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..ops import sketch_ops

BASE = (0.86, 0.86, 0.86, 1.0)
ACCENT = (0.24, 0.86, 0.66, 1.0)
CONSTRUCTION = (0.6, 0.6, 0.6, 0.55)
FIXED = (1.0, 0.62, 0.2, 1.0)
CONFLICT = (1.0, 0.35, 0.3, 1.0)
DIMENSION = (1.0, 0.8, 0.3, 1.0)

_handle = [None]


def _polylines(shader, lines, color, width):
    coords = []
    for line in lines:
        for a, b in zip(line, line[1:]):
            coords.extend(((a[0], a[1], 0.0), (b[0], b[1], 0.0)))
    if not coords:
        return
    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch.draw(shader)


def _squares(shader, centers, color, half):
    verts, indices = [], []
    for x, y in centers:
        n = len(verts)
        verts.extend(((x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half)))
        indices.extend(((n, n + 1, n + 2), (n, n + 2, n + 3)))
    if not verts:
        return
    batch = batch_for_shader(shader, "TRIS", {"pos": verts}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def _text(x, y, text, size, color):
    blf.size(0, size)
    blf.color(0, *color)
    w, _h = blf.dimensions(0, text)
    blf.position(0, x - w / 2, y, 0)
    blf.draw(0, text)


def _length_text(scene, value):
    units = scene.unit_settings
    if units.system == "NONE":
        return f"{value:.4g}"
    return bpy.utils.units.to_string(units.system, "LENGTH", value * units.scale_length, precision=3,
                                     split_unit=False, compatible_unit=False)


def _draw():
    context = bpy.context
    scene = context.scene
    settings = getattr(scene, "param_settings", None)
    wm = context.window_manager
    running = getattr(wm, "param_sketch_running", False)
    if settings is None or not (settings.show_sketch or running):
        return
    node = sketch_ops.active_sketch(context)
    region, rv3d, obj = context.region, context.region_data, context.active_object
    if node is None or region is None or rv3d is None or obj is None or not node.points and not running:
        return
    matrix = obj.matrix_world
    ui = context.preferences.system.ui_scale

    def to2d(x, y):
        co = location_3d_to_region_2d(region, rv3d, matrix @ Vector((x, y, 0.0)))
        return (co.x, co.y) if co is not None else None

    def path(points):
        out = [to2d(x, y) for x, y in points]
        return out if all(p is not None for p in out) else None

    P = node.points
    groups = {"base": [], "selected": [], "construction": []}

    def add(item, points):
        line = path(points)
        if line is not None:
            groups["selected" if item.select else ("construction" if item.construction else "base")].append(line)

    for line in node.lines:
        add(line, [(P[line.a].x, P[line.a].y), (P[line.b].x, P[line.b].y)])
    for c in node.circles:
        cx, cy = P[c.center].x, P[c.center].y
        add(c, [(cx + c.radius * math.cos(math.tau * i / 64), cy + c.radius * math.sin(math.tau * i / 64)) for i in range(65)])
    for arc in node.arcs:
        add(arc, [(P[arc.start].x, P[arc.start].y)] + node.arc_points(arc, 64) + [(P[arc.end].x, P[arc.end].y)])

    gpu.state.blend_set("ALPHA")
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))
    conflict = "Konflikt" in node.sketch_status
    _polylines(shader, groups["construction"], CONSTRUCTION, 1.5 * ui)
    _polylines(shader, groups["base"], CONFLICT if conflict else BASE, 2.5 * ui)
    _polylines(shader, groups["selected"], ACCENT, 3.5 * ui)

    session = sketch_ops.runtime["session"]
    if running and session is not None and session.node == node:
        preview = [p for p in (path(line) for line in session.preview()) if p is not None]
        _polylines(shader, preview, ACCENT, 1.5 * ui)

    flat = gpu.shader.from_builtin("UNIFORM_COLOR")
    flat.bind()
    normal, selected, fixed = [], [], []
    for p in P:
        co = to2d(p.x, p.y)
        if co is not None:
            (selected if p.select else fixed if p.fixed else normal).append(co)
    _squares(flat, normal, BASE, 3.5 * ui)
    _squares(flat, fixed, FIXED, 4.5 * ui)
    _squares(flat, selected, ACCENT, 5.0 * ui)
    if running and session is not None and session.cursor is not None:
        co = to2d(*session.cursor)
        if co is not None:
            _squares(flat, [co], ACCENT, 3.0 * ui)
            if session.snap_label:
                _text(co[0], co[1] + 12 * ui, session.snap_label, int(11 * ui), ACCENT)
    gpu.state.blend_set("NONE")

    # dimensions
    size = int(12 * ui)
    for con in node.constraints:
        if not con.has_value:
            continue
        suffix = f"  ← {con.expression.strip()}" if con.expression.strip() else ""
        if con.kind == "DISTANCE":
            a, b = P[con.p1], P[con.p2]
            co = to2d((a.x + b.x) / 2, (a.y + b.y) / 2)
            text = _length_text(scene, math.hypot(a.x - b.x, a.y - b.y))
        elif con.kind == "RADIUS":
            if con.curve_kind == "CIRCLE":
                c = node.circles[con.curve]
                center, radius = P[c.center], c.radius
            else:
                arc = node.arcs[con.curve]
                center = P[arc.center]
                radius = math.hypot(P[arc.start].x - center.x, P[arc.start].y - center.y)
            co = to2d(center.x + radius * 0.7071, center.y + radius * 0.7071)
            text = "R " + _length_text(scene, radius)
        else:  # ANGLE
            a = P[con.p1]
            co = to2d(a.x, a.y)
            text = f"{math.degrees(con.value):.1f}°"
        if co is not None:
            _text(co[0], co[1] + 8 * ui, text + suffix, size, DIMENSION)


def register():
    if _handle[0] is None:
        _handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle[0], "WINDOW")
        _handle[0] = None
