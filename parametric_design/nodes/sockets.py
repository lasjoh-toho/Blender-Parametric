# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, IntProperty


def _changed(self, _context):
    from ..core import scheduler
    node = self.node
    if hasattr(node, "param_dirty"):
        node.param_dirty = True
    scheduler.request(self.id_data)


class _SocketBase:
    color = (0.6, 0.6, 0.6, 1.0)

    def draw(self, context, layout, node, text):
        if self.is_output or self.is_linked or not hasattr(self, "default_value"):
            layout.label(text=text)
        else:
            layout.prop(self, "default_value", text=text)

    def draw_color(self, context, node):
        return self.color

    @classmethod
    def draw_color_simple(cls):
        return cls.color


class PARAM_SocketGeometry(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketGeometry"
    bl_label = "Geometrie"
    color = (0.0, 0.84, 0.64, 1.0)


class PARAM_SocketLength(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketLength"
    bl_label = "Länge"
    color = (0.63, 0.63, 0.63, 1.0)
    default_value: FloatProperty(subtype="DISTANCE", unit="LENGTH", update=_changed, precision=3)


class PARAM_SocketAngle(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketAngle"
    bl_label = "Winkel"
    color = (0.78, 0.55, 0.3, 1.0)
    default_value: FloatProperty(subtype="ANGLE", unit="ROTATION", update=_changed)


class PARAM_SocketFloat(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketFloat"
    bl_label = "Zahl"
    color = (0.5, 0.5, 0.5, 1.0)
    default_value: FloatProperty(update=_changed, precision=3)


class PARAM_SocketInt(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketInt"
    bl_label = "Ganzzahl"
    color = (0.35, 0.55, 0.36, 1.0)
    default_value: IntProperty(update=_changed)


class PARAM_SocketBool(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketBool"
    bl_label = "Schalter"
    color = (0.8, 0.65, 0.84, 1.0)
    default_value: BoolProperty(update=_changed)


class PARAM_SocketVector(_SocketBase, bpy.types.NodeSocket):
    bl_idname = "PARAM_SocketVector"
    bl_label = "Vektor"
    color = (0.39, 0.39, 0.78, 1.0)
    default_value: FloatVectorProperty(size=3, subtype="XYZ", update=_changed, precision=3)

    def draw(self, context, layout, node, text):
        if self.is_output or self.is_linked:
            layout.label(text=text)
        else:
            col = layout.column(align=True)
            col.label(text=text)
            col.prop(self, "default_value", text="")


classes = (
    PARAM_SocketGeometry,
    PARAM_SocketLength,
    PARAM_SocketAngle,
    PARAM_SocketFloat,
    PARAM_SocketInt,
    PARAM_SocketBool,
    PARAM_SocketVector,
)
