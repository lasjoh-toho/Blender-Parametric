# SPDX-License-Identifier: GPL-3.0-or-later
"""Print check and STL export."""

import json
import os

import bmesh
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper

from ..core import geometry, print_check
from ..core.units import mm_per_unit


# What the last check found, for the highlight in the viewport. Not saved with the file.
runtime = {"object": "", "triangles": {}, "levels": {}, "active": ""}

VERDICTS = {print_check.OK: "Druckbereit", print_check.WARN: "Druckbar mit Hinweisen", print_check.FAIL: "So nicht druckbar"}


def clear_highlight():
    runtime.update(object="", triangles={}, levels={}, active="")


def check(context, obj):
    """Run every check on the evaluated object. Returns (list of Check, summary dict)."""
    scene = context.scene
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    me = evaluated.to_mesh()
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
    finally:
        evaluated.to_mesh_clear()
    try:
        bm.transform(obj.matrix_world)
        data = geometry.stats(bm)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.faces.ensure_lookup_table()
        # scene units, lifted a little off the surface, for the highlight
        lift = max(data["dimensions"]) * 0.002
        world = [[tuple(v.co + f.normal * lift) for v in f.verts] for f in bm.faces]
        scale = mm_per_unit(scene)
        bmesh.ops.scale(bm, vec=(scale, scale, scale), verts=bm.verts[:])
        checks = print_check.run(bm, scene.param_print.as_dict())
    finally:
        bm.free()
    data["dimensions_mm"] = tuple(d * scale for d in data["dimensions"])
    data["volume_cm3"] = data["volume"] * scale ** 3 / 1000.0
    data["level"] = print_check.worst(checks)
    data["ok"] = data["level"] != print_check.FAIL
    runtime.update(
        object=obj.name,
        triangles={c.id: [world[i] for i in c.faces] for c in checks if c.faces},
        levels={c.id: c.level for c in checks},
        active="",
    )
    return checks, data


def report_of(scene):
    """The stored report of the last check as a dict, or None."""
    raw = scene.get("param_print_report")
    if not raw:
        return None
    try:
        report = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return report if isinstance(report, dict) else None


class PARAM_OT_print_check(bpy.types.Operator):
    """Check the active object for 3D printing: closed, size, wall thickness, overhangs, stability"""

    bl_idname = "param.print_check"
    bl_label = "Druck prüfen"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        checks, data = check(context, obj)
        dx, dy, dz = data["dimensions_mm"]
        verdict = VERDICTS[data["level"]]
        context.scene["param_print_report"] = json.dumps({
            "object": obj.name,
            "level": data["level"],
            "verdict": verdict,
            "size": f"{dx:.2f} × {dy:.2f} × {dz:.2f} mm",
            "volume": f"{data['volume_cm3']:.2f} cm³",
            "parts": data["islands"],
            "checks": [c.as_dict() for c in checks],
        })
        problems = [f"{c.label}: {c.text}" for c in checks if c.level != print_check.OK]
        self.report({"INFO"} if data["level"] == print_check.OK else {"WARNING"},
                    verdict + (" · " + problems[0] if problems else f" · {dx:.2f} × {dy:.2f} × {dz:.2f} mm"))
        _redraw(context)
        return {"FINISHED"}


class PARAM_OT_print_highlight(bpy.types.Operator):
    """Show the affected faces in the viewport (again: hide)"""

    bl_idname = "param.print_highlight"
    bl_label = "Stellen zeigen"

    check_id: StringProperty()

    def execute(self, context):
        if self.check_id not in runtime["triangles"]:
            self.report({"INFO"}, "Bitte erst neu prüfen")
            runtime["active"] = ""
        else:
            runtime["active"] = "" if runtime["active"] == self.check_id else self.check_id
        _redraw(context)
        return {"FINISHED"}


def _redraw(context):
    screen = getattr(context, "screen", None)
    for area in (screen.areas if screen else ()):
        if area.type == "VIEW_3D":
            area.tag_redraw()


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


classes = (PARAM_OT_print_check, PARAM_OT_print_highlight, PARAM_OT_export_stl)
