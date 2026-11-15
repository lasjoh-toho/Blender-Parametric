# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, StringProperty

from ..core.evaluator import TREE_ID


class PARAM_NT_tree(bpy.types.NodeTree):
    """Parametric model: tools in the 3D view add nodes here"""

    bl_idname = TREE_ID
    bl_label = "Parametric Tree"
    bl_icon = "MOD_BUILD"

    param_dirty: BoolProperty(name="Veraltet", default=True)
    param_status: StringProperty(name="Status", default="")

    def update(self):
        from ..core import scheduler
        scheduler.request(self)


classes = (PARAM_NT_tree,)
