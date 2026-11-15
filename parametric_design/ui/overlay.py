# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport badges: named parameters next to the active object, snap and sync state."""

import math

import blf
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..ops import graph

_handle = [None]


def _format(node, scene):
    unit = getattr(node, "param_unit", "NUMBER")
    if unit == "ANGLE":
        return f"{math.degrees(node.value):.1f}°"
    if unit == "LENGTH":
        return bpy.utils.units.to_string(scene.unit_settings.system, "LENGTH",
                                         node.value * scene.unit_settings.scale_length, precision=2)
    return f"{node.value:g}"


def _text(x, y, text, size, color):
    font = 0
    try:
        blf.size(font, size)
    except TypeError:  # very old signature
        blf.size(font, size, 72)
    blf.color(font, *color)
    blf.position(font, x, y, 0)
    blf.draw(font, text)


def _draw():
    context = bpy.context
    scene = context.scene
    settings = getattr(scene, "param_settings", None)
    if settings is None or not settings.show_overlay:
        return
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    scale = context.preferences.system.ui_scale
    size = int(13 * scale)
    # status line, bottom left
    ts = scene.tool_settings
    obj = context.active_object
    parts = ["Snap an" if ts.use_snap else "Snap aus"]
    if graph.is_parametric(obj):
        outs = [o for o in obj.param_tree.nodes if o.bl_idname == "PARAM_N_Output" and o.target == obj]
        if outs:
            parts.append("Sync live" if outs[0].sync_mode == "LIVE" else "Sync aufgehoben")
        if obj.param_tree.param_status.startswith("Fehler"):
            parts.append("Fehler")
    _text(int(20 * scale), int(20 * scale), "  ·  ".join(parts), size, (1, 1, 1, 0.8))

    if not graph.is_parametric(obj) or not obj.visible_get():
        return
    params = [n for n in obj.param_tree.nodes if getattr(n, "param_name", "") and hasattr(n, "parameter_value")]
    if not params:
        return
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    top = max(corners, key=lambda c: c.z)
    anchor = location_3d_to_region_2d(region, rv3d, top)
    if anchor is None:
        return
    line = size + int(6 * scale)
    for i, node in enumerate(params[:12]):
        _text(int(anchor.x + 12 * scale), int(anchor.y - i * line), f"{node.param_name} = {_format(node, scene)}",
              size, (1.0, 0.8, 0.3, 0.95))


def register():
    if _handle[0] is None:
        _handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle[0], "WINDOW")
        _handle[0] = None
