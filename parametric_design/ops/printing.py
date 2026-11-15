# SPDX-License-Identifier: GPL-3.0-or-later
"""Print check and STL export."""

import os

import bmesh
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper

from ..core import geometry


def mm_per_unit(scene):
    """How many millimetres one Blender unit is in this scene."""
    units = scene.unit_settings
    if units.system == "NONE":
        return 1.0  # unitless scenes are treated as millimetres
    return units.scale_length * 1000.0


def check(context, obj):
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    me = evaluated.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(obj.matrix_world)
        data = geometry.stats(bm)
        bm.free()
    finally:
        evaluated.to_mesh_clear()
    scale = mm_per_unit(context.scene)
    data["dimensions_mm"] = tuple(d * scale for d in data["dimensions"])
    data["volume_cm3"] = data["volume"] * scale ** 3 / 1000.0
    data["ok"] = data["non_manifold_edges"] == 0 and data["loose_verts"] == 0 and data["faces"] > 0
    return data


class PARAM_OT_print_check(bpy.types.Operator):
    """Check the active object for 3D printing: size, volume, holes (non-manifold edges)"""

    bl_idname = "param.print_check"
    bl_label = "Druck-Check"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        data = check(context, obj)
        dx, dy, dz = data["dimensions_mm"]
        lines = [
            f"Maße: {dx:.2f} × {dy:.2f} × {dz:.2f} mm",
            f"Volumen: {data['volume_cm3']:.2f} cm³",
            f"Teile: {data['islands']}",
            f"Offene Kanten: {data['non_manifold_edges']}",
            f"Lose Punkte: {data['loose_verts']}",
        ]
        verdict = "Druckbereit" if data["ok"] else "Nicht wasserdicht – bitte prüfen"
        context.scene["param_print_report"] = "\n".join([verdict] + lines)
        self.report({"INFO"} if data["ok"] else {"WARNING"}, verdict + " · " + lines[0])
        return {"FINISHED"}


class PARAM_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the active object as STL in millimetres"""

    bl_idname = "param.export_stl"
    bl_label = "STL exportieren"

    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and hasattr(bpy.ops.wm, "stl_export")

    def invoke(self, context, event):
        obj = context.active_object
        blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(blend_dir, bpy.path.clean_name(obj.name) + self.filename_ext)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        obj = context.active_object
        selected = list(context.selected_objects)
        for o in selected:
            o.select_set(False)
        obj.select_set(True)
        try:
            bpy.ops.wm.stl_export(
                filepath=self.filepath,
                export_selected_objects=True,
                apply_modifiers=True,
                use_scene_unit=False,
                global_scale=mm_per_unit(context.scene),
                ascii_format=False,
            )
        finally:
            obj.select_set(False)
            for o in selected:
                o.select_set(True)
        self.report({"INFO"}, f"Exportiert: {self.filepath}")
        return {"FINISHED"}


classes = (PARAM_OT_print_check, PARAM_OT_export_stl)
