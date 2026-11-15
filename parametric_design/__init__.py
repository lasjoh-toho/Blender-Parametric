# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric Design: parametric modelling with viewport tools and a live node graph."""

import bpy

from . import nodes, ops, preferences, props, ui
from .core import scheduler


def register():
    for cls in preferences.classes:
        bpy.utils.register_class(cls)
    props.register()
    nodes.register()
    ops.register()
    ui.register()
    scheduler.register()


def unregister():
    scheduler.unregister()
    ui.unregister()
    ops.unregister()
    nodes.unregister()
    props.unregister()
    for cls in reversed(preferences.classes):
        bpy.utils.unregister_class(cls)
