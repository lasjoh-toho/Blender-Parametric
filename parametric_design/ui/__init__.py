# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import follow, icons, overlay, panels, pie

classes = panels.classes + pie.classes


def register():
    icons.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    pie.register_keymaps()
    bpy.types.VIEW3D_HT_tool_header.append(panels.draw_quick_access)
    if not bpy.app.background:
        overlay.register()
        from . import print_overlay, sketch_overlay
        sketch_overlay.register()
        print_overlay.register()
    follow.register()


def unregister():
    follow.unregister()
    overlay.unregister()
    if not bpy.app.background:
        from . import print_overlay, sketch_overlay
        print_overlay.unregister()
        sketch_overlay.unregister()
    pie.unregister_keymaps()
    bpy.types.VIEW3D_HT_tool_header.remove(panels.draw_quick_access)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    icons.unregister()
