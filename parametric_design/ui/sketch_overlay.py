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
from .overlay import length_text

BASE = (0.97, 0.97, 0.97, 1.0)
HALO = (0.0, 0.0, 0.0, 0.55)  # dark edge under the outline, so it stands out on any model
ACCENT = (0.24, 0.86, 0.66, 1.0)
CONSTRUCTION = (0.62, 0.62, 0.62, 0.6)
FIXED = (1.0, 0.62, 0.2, 1.0)
CONFLICT = (1.0, 0.35, 0.3, 1.0)
DIMENSION = (1.0, 0.8, 0.3, 1.0)
SUGGESTION = (0.75, 0.75, 0.75, 0.75)

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


def _dashed(lines, dash, gap):
    """Cut screen-space polylines into dashes."""
    out = []
    period = dash + gap
    for line in lines:
        travelled = 0.0
        for a, b in zip(line, line[1:]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 1e-6:
                continue
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            position = 0.0
            while position < length:
                phase = (travelled + position) % period
                if phase < dash:
                    end = min(length, position + dash - phase)
                    out.append([(a[0] + ux * position, a[1] + uy * position), (a[0] + ux * end, a[1] + uy * end)])
                    position = end
                else:
                    position += period - phase
            travelled += length
    return out


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
    blf.enable(0, blf.SHADOW)
    blf.shadow(0, 3, 0.0, 0.0, 0.0, 0.9)
    blf.draw(0, text)
    blf.disable(0, blf.SHADOW)


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
    # the outline that builds the part is the strongest element; helper lines stay thin and dashed
    _polylines(shader, _dashed(groups["construction"], 6.0 * ui, 5.0 * ui), CONSTRUCTION, 1.2 * ui)
    _polylines(shader, groups["base"] + groups["selected"], HALO, 7.0 * ui)
    _polylines(shader, groups["base"], CONFLICT if conflict else BASE, 3.5 * ui)
    _polylines(shader, groups["selected"], ACCENT, 4.5 * ui)

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
    _squares(flat, normal + fixed + selected, HALO, 6.5 * ui)
    _squares(flat, normal, BASE, 4.5 * ui)
    _squares(flat, fixed, FIXED, 5.0 * ui)
    _squares(flat, selected, ACCENT, 5.5 * ui)
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
            text = length_text(scene, math.hypot(a.x - b.x, a.y - b.y))
        elif con.kind == "RADIUS":
            if con.curve_kind == "CIRCLE":
                c = node.circles[con.curve]
                center, radius = P[c.center], c.radius
            else:
                arc = node.arcs[con.curve]
                center = P[arc.center]
                radius = math.hypot(P[arc.start].x - center.x, P[arc.start].y - center.y)
            co = to2d(center.x + radius * 0.7071, center.y + radius * 0.7071)
            text = "R " + length_text(scene, radius)
        else:  # ANGLE
            a = P[con.p1]
            co = to2d(a.x, a.y)
            text = f"{math.degrees(con.value):.1f}°"
        if co is not None:
            _text(co[0], co[1] + 8 * ui, text + suffix, size, DIMENSION)

    # suggested dimensions: numbered like the list in the panel
    if settings.show_suggestions:
        for index, item in enumerate(sketch_ops.suggestions(node)):
            if item["kind"] == "DISTANCE":
                a, b = P[item["points"][0]], P[item["points"][1]]
                co = to2d((a.x + b.x) / 2, (a.y + b.y) / 2)
                text = length_text(scene, item["value"])
            else:
                kind, number = item["curve"]
                center = P[node.circles[number].center] if kind == "CIRCLE" else P[node.arcs[number].center]
                co = to2d(center.x + item["value"] * 0.7071, center.y + item["value"] * 0.7071)
                text = "R " + length_text(scene, item["value"])
            if co is not None:
                _text(co[0], co[1] + 8 * ui, f"{index + 1}: {text} ?", size, SUGGESTION)


def register():
    if _handle[0] is None:
        _handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle[0], "WINDOW")
        _handle[0] = None
