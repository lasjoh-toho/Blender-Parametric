# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, PointerProperty

from .core.evaluator import TREE_ID


def _tree_poll(self, tree):
    return tree.bl_idname == TREE_ID


class PARAM_PG_scene(bpy.types.PropertyGroup):
    show_overlay: BoolProperty(
        name="Parameter im Viewport",
        description="Benannte Parameter des aktiven Objekts im 3D-Viewport anzeigen",
        default=True,
    )


classes = (PARAM_PG_scene,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.param_tree = PointerProperty(
        name="Parametric Tree", type=bpy.types.NodeTree, poll=_tree_poll,
        description="Node-Graph, aus dem dieses Objekt aufgebaut wird",
    )
    bpy.types.Scene.param_settings = PointerProperty(type=PARAM_PG_scene)


def unregister():
    del bpy.types.Scene.param_settings
    del bpy.types.Object.param_tree
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
