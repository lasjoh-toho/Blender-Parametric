# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import printing, sketch_ops, sync, tools, workspace

@bpy.app.handlers.persistent
def _reset_sketch_tool(_dummy):
    sketch_ops.runtime["session"] = None
    for wm in bpy.data.window_managers:
        wm.param_sketch_running = False


classes = tools.classes + sync.classes + workspace.classes + printing.classes + sketch_ops.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    sketch_ops.register_props()
    bpy.app.handlers.load_post.append(_reset_sketch_tool)


def unregister():
    if _reset_sketch_tool in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_sketch_tool)
    sketch_ops.runtime["session"] = None
    sketch_ops.unregister_props()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
