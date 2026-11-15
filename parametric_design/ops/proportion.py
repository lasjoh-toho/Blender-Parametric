# SPDX-License-Identifier: GPL-3.0-or-later
"""Proportion locks between parameters and the settings dialog of one parameter."""

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from ..nodes import nodes as node_types
from . import graph


def active_tree(context):
    space = context.space_data
    if space is not None and space.type == "NODE_EDITOR":
        tree = getattr(space, "edit_tree", None)
        if tree is not None and tree.bl_idname == graph.TREE_ID:
            return tree
    obj = context.active_object
    return obj.param_tree if graph.is_parametric(obj) else None


def parameters(tree):
    return [n for n in tree.nodes if getattr(n, "param_name", "") and hasattr(n, "parameter_value")]


def lock(tree, nodes, kind):
    """Create a proportion group from parameter nodes. Returns the group or an error text."""
    if len(nodes) < 2:
        return "Mindestens zwei Parameter auswählen"
    if len({n.param_unit for n in nodes}) > 1:
        return "Nur Parameter derselben Art lassen sich verbinden"
    for node in nodes:
        if node_types.proportion_of(tree, node) is not None:
            return f"{node.param_name} gehört schon zu einer Sperre"
        if kind == "RATIO" and abs(node.value) < 1e-9:
            return f"{node.param_name} ist 0, damit gibt es kein Verhältnis"
    group = tree.param_proportions.add()
    group.kind = kind
    for node in nodes:
        member = group.members.add()
        member.node = node.name
        member.factor = node.value
        node.last_value = node.value
        node.has_last = True
        node.pick = False
    return group


def describe(tree, group):
    """Short text such as "breite : tiefe = 2 : 1"."""
    members = [(tree.nodes.get(m.node), m.factor) for m in group.members]
    members = [(n, f) for n, f in members if n is not None]
    if not members:
        return "(leer)"
    names = [n.param_name for n, _f in members]
    if group.kind == "RATIO":
        smallest = min(abs(f) for _n, f in members) or 1.0
        return " : ".join(names) + " = " + " : ".join(f"{f / smallest:.3g}" for _n, f in members)
    first = members[0][1]
    return ", ".join([names[0]] + [f"{n.param_name} {'+' if f - first >= 0 else '−'}{abs(f - first):.4g}"
                                   for n, f in members[1:]])


class PARAM_OT_proportion_lock(bpy.types.Operator):
    """Lock the selected parameters to each other: change one and the others follow"""

    bl_idname = "param.proportion_lock"
    bl_label = "Proportion sperren"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[
        ("RATIO", "Verhältnis", "Die Maße ändern sich gemeinsam im festen Verhältnis"),
        ("DIFFERENCE", "Differenz", "Der Abstand zwischen den Maßen bleibt gleich, z. B. Spiel einer Passung"),
    ])

    @classmethod
    def description(cls, context, props):
        return next(i[2] for i in cls.__annotations__["kind"].keywords["items"] if i[0] == props.kind)

    @classmethod
    def poll(cls, context):
        tree = active_tree(context)
        return tree is not None and sum(1 for n in parameters(tree) if n.pick) >= 2

    def execute(self, context):
        tree = active_tree(context)
        result = lock(tree, [n for n in parameters(tree) if n.pick], self.kind)
        if isinstance(result, str):
            self.report({"WARNING"}, result)
            return {"CANCELLED"}
        return {"FINISHED"}


class PARAM_OT_proportion_unlock(bpy.types.Operator):
    """Release this proportion lock"""

    bl_idname = "param.proportion_unlock"
    bl_label = "Sperre lösen"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        tree = active_tree(context)
        if tree is None or not 0 <= self.index < len(tree.param_proportions):
            return {"CANCELLED"}
        tree.param_proportions.remove(self.index)
        return {"FINISHED"}


class PARAM_OT_parameter_settings(bpy.types.Operator):
    """Name, range and lock of this parameter"""

    bl_idname = "param.parameter_settings"
    bl_label = "Parameter"

    node_name: StringProperty()

    def _node(self, context):
        tree = active_tree(context)
        return tree.nodes.get(self.node_name) if tree else None

    def invoke(self, context, event):
        if self._node(context) is None:
            return {"CANCELLED"}
        return context.window_manager.invoke_popup(self, width=260)

    def draw(self, context):
        node = self._node(context)
        if node is None:
            return
        layout = self.layout
        layout.prop(node, "param_name", text="Name")
        node.draw_range(layout)
        layout.prop(node, "locked", icon="LOCKED" if node.locked else "UNLOCKED")
        layout.prop(node, "expose")

    def execute(self, context):
        return {"FINISHED"}


classes = (PARAM_OT_proportion_lock, PARAM_OT_proportion_unlock, PARAM_OT_parameter_settings)
