# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import printing, sync, tools, workspace

classes = tools.classes + sync.classes + workspace.classes + printing.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
