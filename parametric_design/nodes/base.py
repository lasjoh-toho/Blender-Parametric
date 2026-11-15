# SPDX-License-Identifier: GPL-3.0-or-later
from bpy.props import BoolProperty, StringProperty

from ..core.evaluator import TREE_ID


def changed(self, _context):
    """Update callback for node properties."""
    from ..core import scheduler
    self.param_dirty = True
    scheduler.request(self.id_data)


class ParamNode:
    """Mixin for every node of the Parametric Tree."""

    param_dirty: BoolProperty(default=True)
    param_error: StringProperty(default="")

    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == TREE_ID

    # Sub-classes call these from ``init``.
    def add_input(self, socket_type, name, default=None):
        sock = self.inputs.new(socket_type, name)
        if default is not None:
            sock.default_value = default
        return sock

    def add_output(self, socket_type, name):
        return self.outputs.new(socket_type, name)

    def draw_buttons(self, context, layout):
        self.draw_props(context, layout)
        if self.param_error:
            box = layout.box()
            box.alert = True
            box.label(text=self.param_error, icon="ERROR")

    def draw_buttons_ext(self, context, layout):
        self.draw_buttons(context, layout)

    def draw_props(self, context, layout):
        pass

    def evaluate(self, ectx):
        raise NotImplementedError
