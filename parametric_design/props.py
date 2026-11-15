# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, PointerProperty

from .core import print_check
from .core.evaluator import TREE_ID


def _tree_poll(self, tree):
    return tree.bl_idname == TREE_ID


class PARAM_PG_scene(bpy.types.PropertyGroup):
    show_overlay: BoolProperty(
        name="Parameter im Viewport",
        description="Benannte Parameter des aktiven Objekts im 3D-Viewport anzeigen",
        default=True,
    )
    profile_mode: EnumProperty(
        name="Profil",
        description="Was mit einem neuen Profil geschieht",
        items=[("EXTRUDE", "Extrude", "Profil in die Höhe ziehen"), ("REVOLVE", "Revolve", "Profil um die Z-Achse drehen")],
        default="EXTRUDE",
    )
    show_sketch: BoolProperty(
        name="Skizze im Viewport",
        description="Skizze des aktiven Objekts mit Maßen im 3D-Viewport anzeigen",
        default=True,
    )
    show_suggestions: BoolProperty(
        name="Maße vorschlagen",
        description="Maße zeigen, die sich als Parameter eignen: jedes schließt einen offenen Freiheitsgrad der Skizze",
        default=True,
    )
    sketch_grid: FloatProperty(
        name="Raster",
        description="Rasterweite, auf die Skizzenpunkte bei aktivem Snap einrasten (0 = aus)",
        default=1.0, min=0.0, subtype="DISTANCE",
    )


def _apply_preset(self, _context):
    preset = print_check.PRESETS.get(self.preset)
    if preset is None:
        return
    for key, value in preset.items():
        if key == "bed":
            self.bed = value
        else:
            setattr(self, key, value)


class PARAM_PG_print(bpy.types.PropertyGroup):
    """Print profile of the scene. Every value is in millimetres or degrees."""

    preset: EnumProperty(
        name="Druckprofil",
        description="Vorgaben für das Druckverfahren laden",
        items=[("FDM", "FDM", "Filamentdruck, 0,4 mm Düse"), ("RESIN", "Harz", "Harzdruck (SLA/MSLA)")],
        default="FDM", update=_apply_preset,
    )
    nozzle: FloatProperty(name="Düse / Auflösung (mm)", default=0.4, min=0.01, soft_max=1.2, precision=2)
    layer_height: FloatProperty(name="Schichthöhe (mm)", default=0.2, min=0.01, soft_max=0.6, precision=2)
    min_wall: FloatProperty(name="Mindestwand (mm)", description="Wände darunter gelten als zu dünn",
                            default=0.8, min=0.05, soft_max=5.0, precision=2)
    min_detail: FloatProperty(name="Kleinstes Detail (mm)", default=0.4, min=0.01, soft_max=2.0, precision=2)
    max_overhang: FloatProperty(name="Max. Überhang (°)", description="Winkel zur Senkrechten, bis zu dem ohne Stützen gedruckt wird",
                                default=45.0, min=0.0, max=90.0, precision=0)
    clearance: FloatProperty(name="Passungsspiel (mm)", default=0.2, min=0.0, soft_max=1.0, precision=2)
    bed: FloatVectorProperty(name="Bauraum (mm)", size=3, default=(220.0, 220.0, 250.0), min=1.0, precision=0)

    def as_dict(self):
        return {
            "nozzle": self.nozzle, "layer_height": self.layer_height, "min_wall": self.min_wall,
            "min_detail": self.min_detail, "max_overhang": self.max_overhang, "clearance": self.clearance,
            "bed": tuple(self.bed),
        }


classes = (PARAM_PG_scene, PARAM_PG_print)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.param_tree = PointerProperty(
        name="Parametric Tree", type=bpy.types.NodeTree, poll=_tree_poll,
        description="Node-Graph, aus dem dieses Objekt aufgebaut wird",
    )
    bpy.types.Scene.param_settings = PointerProperty(type=PARAM_PG_scene)
    bpy.types.Scene.param_print = PointerProperty(type=PARAM_PG_print)


def unregister():
    del bpy.types.Scene.param_print
    del bpy.types.Scene.param_settings
    del bpy.types.Object.param_tree
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
