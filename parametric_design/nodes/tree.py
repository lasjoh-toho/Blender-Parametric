# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty

from ..core.evaluator import TREE_ID


class PARAM_PG_proportion_member(bpy.types.PropertyGroup):
    node: StringProperty()  # name of the parameter node
    factor: FloatProperty()  # its value when the group was locked


class PARAM_PG_proportion(bpy.types.PropertyGroup):
    """Parameters that keep their ratio or their difference when one of them changes."""

    kind: EnumProperty(items=[
        ("RATIO", "Verhältnis", "Die Maße ändern sich gemeinsam im festen Verhältnis"),
        ("DIFFERENCE", "Differenz", "Der Abstand zwischen den Maßen bleibt gleich"),
    ])
    members: CollectionProperty(type=PARAM_PG_proportion_member)


class PARAM_NT_tree(bpy.types.NodeTree):
    """Parametric model: tools in the 3D view add nodes here"""

    bl_idname = TREE_ID
    bl_label = "Parametric Tree"
    bl_icon = "MOD_BUILD"

    param_dirty: BoolProperty(name="Veraltet", default=True)
    param_status: StringProperty(name="Status", default="")
    param_notice: StringProperty(name="Hinweis", default="")  # why the last change of a parameter was held back
    param_proportions: CollectionProperty(type=PARAM_PG_proportion)

    def update(self):
        from ..core import scheduler
        scheduler.request(self)


classes = (PARAM_PG_proportion_member, PARAM_PG_proportion, PARAM_NT_tree)
