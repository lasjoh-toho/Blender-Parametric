# SPDX-License-Identifier: GPL-3.0-or-later
"""Radial (pie) menu for quick access with a stylus."""

import bpy

from . import icons


class PARAM_MT_pie(bpy.types.Menu):
    bl_idname = "PARAM_MT_pie"
    bl_label = "Parametric"

    def draw(self, context):
        pie = self.layout.menu_pie()
        ts = context.scene.tool_settings
        # Order of pie slots: W, E, S, N, NW, NE, SW, SE
        pie.operator("param.set_sync", text="Sync aufheben", icon_value=icons.get("unsync")).mode = "FROZEN"
        pie.operator("param.group_objects", text="Gruppe", icon_value=icons.get("group"))
        pie.operator("param.set_sync", text="Sync", icon_value=icons.get("sync")).mode = "LIVE"
        pie.operator("param.add_part", text="Box", icon_value=icons.get("box")).kind = "BOX"
        pie.operator("ed.undo", text="Undo", icon_value=icons.get("undo"))
        pie.operator("param.toggle_snap", text="Snap aus" if ts.use_snap else "Snap an", icon_value=icons.get("snap"))
        pie.operator("transform.translate", text="Move", icon_value=icons.get("transform"))
        pie.operator("param.duplicate", text="Duplikat", icon_value=icons.get("duplicate")).mode = "COPY"


classes = (PARAM_MT_pie,)

addon_keymaps = []


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc is None:
        return
    for km_name, space in (("3D View", "VIEW_3D"), ("Node Editor", "NODE_EDITOR")):
        km = kc.keymaps.new(name=km_name, space_type=space)
        kmi = km.keymap_items.new("wm.call_menu_pie", "Q", "PRESS", shift=True, alt=True)
        kmi.properties.name = PARAM_MT_pie.bl_idname
        addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    addon_keymaps.clear()
