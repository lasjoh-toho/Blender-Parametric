# SPDX-License-Identifier: GPL-3.0-or-later
"""The node editor follows the active object (unless it is pinned)."""

import bpy
from bpy.app.handlers import persistent

from ..ops import graph
from ..ops.workspace import show_tree_in_editors

_owner = object()


def _on_active_changed():
    context = bpy.context
    obj = context.view_layer.objects.active if context.view_layer else None
    if graph.is_parametric(obj):
        show_tree_in_editors(context, obj.param_tree)


def _subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, "active"),
        owner=_owner,
        args=(),
        notify=_on_active_changed,
    )


@persistent
def _on_load(_dummy):
    _subscribe()


def register():
    _subscribe()
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    bpy.msgbus.clear_by_owner(_owner)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
