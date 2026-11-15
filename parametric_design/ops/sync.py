# SPDX-License-Identifier: GPL-3.0-or-later
"""Sync, freeze, re-link and bake."""

import bpy
from bpy.props import BoolProperty, EnumProperty

from ..core import evaluator, scheduler
from . import graph


def _outputs(obj):
    tree = obj.param_tree
    outs = [o for o in evaluator.output_nodes(tree) if o.target == obj]
    if not outs and obj.data is not None:
        # instances share the mesh with the output target
        outs = [o for o in evaluator.output_nodes(tree) if o.target is not None and o.target.data == obj.data]
    return outs


class _ActiveParametric:
    @classmethod
    def poll(cls, context):
        if not graph.is_parametric(context.active_object):
            cls.poll_message_set("Wähle zuerst ein parametrisches Objekt")
            return False
        return True


class PARAM_OT_set_sync(_ActiveParametric, bpy.types.Operator):
    """Live: rebuild on every change. Frozen: keep the graph but stop updating the mesh"""

    bl_idname = "param.set_sync"
    bl_label = "Sync"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        items=[("LIVE", "Sync (live)", "", "LINKED", 0), ("FROZEN", "Sync aufheben", "", "UNLINKED", 1), ("TOGGLE", "Umschalten", "", "ARROW_LEFTRIGHT", 2)],
        default="TOGGLE",
    )

    def execute(self, context):
        obj = context.active_object
        outs = _outputs(obj)
        if not outs:
            self.report({"WARNING"}, "Kein Output-Node für dieses Objekt")
            return {"CANCELLED"}
        mode = self.mode
        if mode == "TOGGLE":
            mode = "FROZEN" if outs[0].sync_mode == "LIVE" else "LIVE"
        with scheduler.suspended():
            for out in outs:
                out.sync_mode = mode
        if mode == "LIVE":
            evaluator.evaluate_tree(obj.param_tree, force=True)
        self.report({"INFO"}, "Sync live" if mode == "LIVE" else "Sync aufgehoben (eingefroren)")
        return {"FINISHED"}


class PARAM_OT_relink(_ActiveParametric, bpy.types.Operator):
    """Switch back to live sync and rebuild right away"""

    bl_idname = "param.relink"
    bl_label = "Re-link"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return bpy.ops.param.set_sync(mode="LIVE")


class PARAM_OT_recalculate(bpy.types.Operator):
    """Rebuild the active object (or every parametric object) from its graph now"""

    bl_idname = "param.recalculate"
    bl_label = "Neu berechnen"
    bl_options = {"REGISTER", "UNDO"}

    all_objects: BoolProperty(name="Alle", default=False)

    def execute(self, context):
        if self.all_objects:
            trees = scheduler.parametric_trees()
        else:
            obj = context.active_object
            trees = [obj.param_tree] if graph.is_parametric(obj) else []
            space = context.space_data
            if not trees and getattr(space, "edit_tree", None) is not None and space.edit_tree.bl_idname == evaluator.TREE_ID:
                trees = [space.edit_tree]
        for tree in trees:
            evaluator.evaluate_tree(tree, force=True)
            for dep in scheduler.dependents(tree):
                scheduler.request(dep)
        scheduler.flush()
        return {"FINISHED"}


class PARAM_OT_bake(_ActiveParametric, bpy.types.Operator):
    """Detach the graph: the object keeps its current mesh and becomes a normal mesh object"""

    bl_idname = "param.bake"
    bl_label = "Bake"
    bl_options = {"REGISTER", "UNDO"}

    remove_unused: BoolProperty(name="Unbenutzten Graph löschen", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = context.active_object
        tree = obj.param_tree
        # make sure the mesh is current, then give the object its own copy
        evaluator.evaluate_tree(tree, force=True)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        with scheduler.suspended():
            for out in evaluator.output_nodes(tree):
                if out.target == obj:
                    out.target = None
        obj.param_tree = None
        if self.remove_unused and not graph.object_trees_using(tree) and tree.users <= 1:
            bpy.data.node_groups.remove(tree)
        self.report({"INFO"}, f"{obj.name} ist jetzt ein normales Mesh")
        return {"FINISHED"}


classes = (
    PARAM_OT_set_sync,
    PARAM_OT_relink,
    PARAM_OT_recalculate,
    PARAM_OT_bake,
)
