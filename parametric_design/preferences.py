# SPDX-License-Identifier: GPL-3.0-or-later
import bpy


class PARAM_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Radialmenü (Pie) für Stift und Schnellzugriff", icon="KEYINGSET")
        layout.label(text="Tipp: Lege eine Stift-Seitentaste in den Tablet-Einstellungen auf diese Tastenkombination.")
        from .ui.pie import addon_keymaps
        import rna_keymap_ui
        kc = context.window_manager.keyconfigs.user
        col = layout.column()
        for km_addon, kmi_addon in addon_keymaps:
            km = kc.keymaps.get(km_addon.name)
            if km is None:
                continue
            for kmi in km.keymap_items:
                if kmi.idname == kmi_addon.idname and getattr(kmi.properties, "name", "") == kmi_addon.properties.name:
                    col.context_pointer_set("keymap", km)
                    rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
                    break


classes = (PARAM_AP_preferences,)
