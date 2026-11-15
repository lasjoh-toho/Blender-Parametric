# SPDX-License-Identifier: GPL-3.0-or-later
"""Colours the faces a print check complains about."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..core import print_check
from ..ops import printing

COLORS = {
    print_check.FAIL: (1.0, 0.25, 0.2, 0.6),
    print_check.WARN: (1.0, 0.75, 0.1, 0.6),
    print_check.OK: (0.24, 0.86, 0.66, 0.6),
}

_handle = [None]


def _draw():
    runtime = printing.runtime
    triangles = runtime["triangles"].get(runtime["active"])
    if not triangles or runtime["object"] not in bpy.data.objects:
        return
    coords = [co for tri in triangles for co in tri]
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": coords})
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.face_culling_set("NONE")
    shader.bind()
    shader.uniform_float("color", COLORS.get(runtime["levels"].get(runtime["active"]), COLORS[print_check.WARN]))
    batch.draw(shader)
    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("NONE")


def register():
    if _handle[0] is None:
        _handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW")


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle[0], "WINDOW")
        _handle[0] = None
