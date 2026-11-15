# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from ..core.evaluator import TREE_ID
from . import base, nodes, sockets, tree


def _menu_id(index):
    return f"PARAM_MT_add_{index}"


def _make_menu(index, label, node_ids):
    def draw(self, context):
        layout = self.layout
        for node_id in node_ids:
            cls = getattr(bpy.types, node_id, None)
            if cls is None:
                continue
            op = layout.operator("node.add_node", text=cls.bl_label, icon=getattr(cls, "bl_icon", "NONE"))
            op.type = node_id
            op.use_transform = True

    return type(_menu_id(index), (bpy.types.Menu,), {
        "bl_idname": _menu_id(index),
        "bl_label": label,
        "draw": draw,
    })


_menus = [_make_menu(i, label, ids) for i, (label, ids) in enumerate(nodes.CATEGORIES)]


def _draw_add_menu(self, context):
    space = context.space_data
    if getattr(space, "tree_type", "") != TREE_ID:
        return
    layout = self.layout
    for menu in _menus:
        layout.menu(menu.bl_idname)


classes = sockets.classes + tree.classes + nodes.classes + tuple(_menus)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.append(_draw_add_menu)


def unregister():
    bpy.types.NODE_MT_add.remove(_draw_add_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
