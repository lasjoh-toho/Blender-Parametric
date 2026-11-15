# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import follow, overlay, panels, pie

classes = panels.classes + pie.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    pie.register_keymaps()
    if not bpy.app.background:
        overlay.register()
    follow.register()


def unregister():
    follow.unregister()
    overlay.unregister()
    pie.unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
