# SPDX-License-Identifier: GPL-3.0-or-later
"""Workspace layout and units for 3D printing."""

import bpy

from ..core.evaluator import TREE_ID
from . import graph


def show_tree_in_editors(context, tree, force=False):
    """Show ``tree`` in every Parametric node editor that is not pinned."""
    if tree is None:
        return
    wm = context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != "NODE_EDITOR":
                continue
            space = area.spaces.active
            if space.tree_type != TREE_ID or (space.pin and not force):
                continue
            if space.node_tree != tree:
                space.node_tree = tree
                area.tag_redraw()


class PARAM_OT_setup_units(bpy.types.Operator):
    """Metric units with 1 Blender unit = 1 mm, ready for 3D printing"""

    bl_idname = "param.setup_units"
    bl_label = "Einheiten: Millimeter"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        units = context.scene.unit_settings
        units.system = "METRIC"
        units.scale_length = 0.001
        units.length_unit = "MILLIMETERS"
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    space = area.spaces.active
                    space.clip_start = min(space.clip_start, 0.1)
                    space.clip_end = max(space.clip_end, 10000.0)
        self.report({"INFO"}, "Einheiten: 1 Blender-Einheit = 1 mm")
        return {"FINISHED"}


class PARAM_OT_setup_workspace(bpy.types.Operator):
    """Split the 3D viewport: model on top, node graph below, tool box in the side bar"""

    bl_idname = "param.setup_workspace"
    bl_label = "Parametrischer Arbeitsbereich"
    bl_options = {"REGISTER"}

    def execute(self, context):
        screen = context.screen
        area = context.area if context.area and context.area.type == "VIEW_3D" else None
        if area is None:
            areas = [a for a in screen.areas if a.type == "VIEW_3D"]
            if not areas:
                self.report({"ERROR"}, "Kein 3D-Viewport gefunden")
                return {"CANCELLED"}
            area = max(areas, key=lambda a: a.width * a.height)
        # Already there?
        if any(a.type == "NODE_EDITOR" and a.spaces.active.tree_type == TREE_ID for a in screen.areas):
            self._finish(context, area)
            return {"FINISHED"}
        before = set(screen.areas[:])
        region = next(r for r in area.regions if r.type == "WINDOW")
        with context.temp_override(window=context.window, screen=screen, area=area, region=region):
            bpy.ops.screen.area_split(direction="HORIZONTAL", factor=0.38)
        new_areas = [a for a in screen.areas if a not in before]
        if not new_areas:
            self.report({"ERROR"}, "Der Viewport konnte nicht geteilt werden")
            return {"CANCELLED"}
        pair = [area, new_areas[0]]
        bottom = min(pair, key=lambda a: a.y)
        top = max(pair, key=lambda a: a.y)
        bottom.type = "NODE_EDITOR"
        bottom.ui_type = TREE_ID
        top.type = "VIEW_3D"
        self._finish(context, top)
        return {"FINISHED"}

    def _finish(self, context, view_area):
        space = view_area.spaces.active
        if hasattr(space, "show_region_ui"):
            space.show_region_ui = True
        obj = context.active_object
        if graph.is_parametric(obj):
            show_tree_in_editors(context, obj.param_tree, force=True)


classes = (PARAM_OT_setup_units, PARAM_OT_setup_workspace)
