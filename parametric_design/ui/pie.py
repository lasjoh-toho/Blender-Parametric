# SPDX-License-Identifier: GPL-3.0-or-later
"""Radial (pie) menu for quick access with a stylus."""

import bpy


class PARAM_MT_pie(bpy.types.Menu):
    bl_idname = "PARAM_MT_pie"
    bl_label = "Parametric"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # Order of pie slots: W, E, S, N, NW, NE, SW, SE
        pie.operator("param.add_part", text="Box", icon="MESH_CUBE").kind = "BOX"
        pie.operator("param.add_part", text="Zylinder", icon="MESH_CYLINDER").kind = "CYLINDER"
        ts = context.scene.tool_settings
        pie.operator("param.toggle_snap", text="Snap aus" if ts.use_snap else "Snap an",
                     icon="SNAP_ON" if ts.use_snap else "SNAP_OFF")
        op = pie.operator("param.add_part", text="Extrudieren", icon="MOD_SOLIDIFY")
        op.kind = "RECTANGLE"
        op.profile_mode = "EXTRUDE"
        pie.operator("param.add_operation", text="Bevel", icon="MOD_BEVEL").kind = "BEVEL"
        pie.operator("param.add_operation", text="Array", icon="MOD_ARRAY").kind = "LINEAR_ARRAY"
        pie.operator("param.set_sync", text="Sync umschalten", icon="ARROW_LEFTRIGHT").mode = "TOGGLE"
        pie.operator("param.boolean", text="Boolean Differenz", icon="SELECT_SUBTRACT").operation = "DIFFERENCE"


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
