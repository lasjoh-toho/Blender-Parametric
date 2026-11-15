# SPDX-License-Identifier: GPL-3.0-or-later
"""Operations that bmesh does not offer, done with Blender's own modifiers.

The input bmesh is written to a short-lived helper object, a modifier is added,
the depsgraph evaluates it and the result is read back into a new bmesh. The
helper objects are removed again before the function returns, so nothing is
ever drawn.
"""

import bmesh
import bpy

from .geometry import GeometryError

TMP_PREFIX = "_param_tmp"


def _scene():
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        scene = bpy.data.scenes[0]
    return scene


def _depsgraph(scene):
    view_layer = getattr(bpy.context, "view_layer", None)
    if view_layer is None or view_layer.id_data != scene:
        view_layer = scene.view_layers[0]
    return view_layer.depsgraph


def _helper(bm, scene, name):
    me = bpy.data.meshes.new(TMP_PREFIX + name)
    bm.to_mesh(me)
    obj = bpy.data.objects.new(TMP_PREFIX + name, me)
    scene.collection.objects.link(obj)
    return obj


def _cleanup(objects):
    for obj in objects:
        me = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def run_modifier(bm, configure, operands=()):
    """Apply one modifier to ``bm`` and return the result as a new bmesh.

    ``configure(obj, operand_objects)`` adds and sets up the modifier.
    ``operands`` are extra bmeshes (e.g. the cutter of a boolean).
    """
    scene = _scene()
    created = []
    try:
        obj = _helper(bm, scene, "main")
        created.append(obj)
        operand_objs = []
        for i, op_bm in enumerate(operands):
            o = _helper(op_bm, scene, f"op{i}")
            o.hide_render = True
            created.append(o)
            operand_objs.append(o)
        configure(obj, operand_objs)
        depsgraph = _depsgraph(scene)
        depsgraph.update()
        evaluated = obj.evaluated_get(depsgraph)
        me = evaluated.to_mesh()
        try:
            out = bmesh.new()
            out.from_mesh(me)
        finally:
            evaluated.to_mesh_clear()
        return out
    finally:
        _cleanup(created)


def boolean(a, b, operation):
    """``operation`` is 'UNION', 'DIFFERENCE' or 'INTERSECT'."""
    if not b.verts:
        if operation == "INTERSECT":
            return bmesh.new()
        return a.copy()
    if not a.verts:
        return b.copy() if operation == "UNION" else bmesh.new()

    def configure(obj, operands):
        mod = obj.modifiers.new("Boolean", "BOOLEAN")
        mod.operation = operation
        mod.solver = "EXACT"
        mod.object = operands[0]

    return run_modifier(a, configure, operands=(b,))


def subdivide_smooth(bm, levels):
    levels = max(0, min(6, int(levels)))
    if levels == 0:
        return bm.copy()

    def configure(obj, _operands):
        mod = obj.modifiers.new("Smooth", "SUBSURF")
        mod.levels = levels
        mod.render_levels = levels

    return run_modifier(bm, configure)


def shell(bm, thickness, inward=True):
    if abs(thickness) < 1e-6:
        raise GeometryError("Die Wandstärke darf nicht 0 sein")

    def configure(obj, _operands):
        mod = obj.modifiers.new("Shell", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = -1.0 if inward else 1.0
        mod.use_even_offset = True
        mod.use_quality_normals = True

    return run_modifier(bm, configure)
