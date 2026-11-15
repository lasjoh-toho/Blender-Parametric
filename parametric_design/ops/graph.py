# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers that build and edit Parametric Trees for the viewport tools."""

import bpy
from mathutils import Vector

from ..core import evaluator, scheduler
from ..core.evaluator import TREE_ID

NODE_GAP = 220

PRIMITIVES = {
    "BOX": ("PARAM_N_Box", "Box"),
    "CYLINDER": ("PARAM_N_Cylinder", "Zylinder"),
    "SPHERE": ("PARAM_N_Sphere", "Kugel"),
    "CONE": ("PARAM_N_Cone", "Kegel"),
}

PROFILES = {
    "RECTANGLE": ("PARAM_N_Rectangle", "Rechteck"),
    "CIRCLE": ("PARAM_N_Circle", "Kreis"),
    "POLYGON": ("PARAM_N_Polygon", "Polygon"),
    "POLYLINE": ("PARAM_N_Polyline", "Polylinie"),
    "SKETCH": ("PARAM_N_Sketch", "Skizze"),
}

OPERATIONS = {
    "TRANSFORM": "PARAM_N_Transform",
    "BEVEL": "PARAM_N_Bevel",
    "SMOOTH": "PARAM_N_Smooth",
    "SHELL": "PARAM_N_Shell",
    "MIRROR": "PARAM_N_Mirror",
    "LINEAR_ARRAY": "PARAM_N_LinearArray",
    "RADIAL_ARRAY": "PARAM_N_RadialArray",
    "BOOLEAN": "PARAM_N_Boolean",
}


def is_parametric(obj):
    return obj is not None and obj.type == "MESH" and obj.param_tree is not None


def new_tree(name):
    return bpy.data.node_groups.new(name, TREE_ID)


def add_node(tree, idname, location=(0, 0), **inputs):
    node = tree.nodes.new(idname)
    node.location = location
    for name, value in inputs.items():
        node.inputs[name].default_value = value
    return node


def first_geometry_input(node):
    for sock in node.inputs:
        if sock.bl_idname == evaluator.GEOMETRY:
            return sock
    return None


def geometry_output(node):
    for sock in node.outputs:
        if sock.bl_idname == evaluator.GEOMETRY:
            return sock
    return None


def output_for(tree, obj=None):
    outs = evaluator.output_nodes(tree)
    for out in outs:
        if obj is not None and out.target == obj:
            return out
    return outs[0] if outs else None


def source_of(socket):
    return socket.links[0].from_socket if socket.is_linked else None


def shift_right(tree, from_x, amount=NODE_GAP):
    for node in tree.nodes:
        if node.location.x >= from_x - 1:
            node.location.x += amount


def insert_before_output(tree, out, node):
    """Put ``node`` between the output node and whatever feeds it."""
    target_in = out.inputs["Geometrie"]
    src = source_of(target_in)
    shift_right(tree, out.location.x)
    node.location = (out.location.x - NODE_GAP, out.location.y)
    geo_in = first_geometry_input(node)
    if src is not None and geo_in is not None:
        tree.links.new(src, geo_in)
    tree.links.new(geometry_output(node), target_in)
    tree.nodes.active = node
    return node


def build_part(tree, kind, location, profile_mode="EXTRUDE"):
    """Add the nodes for a primitive or an extruded/revolved profile; return its geometry output socket."""
    x, y = location
    if kind in PRIMITIVES:
        node = add_node(tree, PRIMITIVES[kind][0], (x, y))
        tree.nodes.active = node
        return geometry_output(node)
    if kind in PROFILES:
        prof = add_node(tree, PROFILES[kind][0], (x - NODE_GAP, y))
        if profile_mode == "REVOLVE":
            op = add_node(tree, "PARAM_N_Revolve", (x, y))
            if kind == "RECTANGLE":
                prof.inputs["Breite"].default_value = 10.0
                prof.inputs["Höhe"].default_value = 30.0
            elif kind == "POLYLINE":
                op.inputs["Achsabstand"].default_value = 0.0
        else:
            op = add_node(tree, "PARAM_N_Extrude", (x, y))
        tree.links.new(geometry_output(prof), op.inputs["Profil"])
        tree.nodes.active = op
        return geometry_output(op)
    raise ValueError(kind)


def part_label(kind):
    if kind in PRIMITIVES:
        return PRIMITIVES[kind][1]
    if kind in PROFILES:
        return PROFILES[kind][1]
    return kind.title()


def create_object(context, name, build):
    """Create a mesh object driven by a new tree. ``build(tree)`` returns the geometry socket for the output."""
    with scheduler.suspended():
        tree = new_tree(name)
        out = add_node(tree, "PARAM_N_Output", (NODE_GAP, 0))
        sock = build(tree)
        if sock is not None:
            tree.links.new(sock, out.inputs["Geometrie"])
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        collection = context.collection or context.scene.collection
        collection.objects.link(obj)
        obj.location = context.scene.cursor.location
        out.target = obj
        obj.param_tree = tree
    select_only(context, obj)
    evaluator.evaluate_tree(tree, force=True)
    return obj, tree


def select_only(context, obj):
    for o in context.view_layer.objects:
        if o.select_get():
            o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def add_part_to(context, obj, kind, profile_mode="EXTRUDE"):
    """Add a part to an existing parametric object (joined with what is there)."""
    tree = obj.param_tree
    out = output_for(tree, obj)
    with scheduler.suspended():
        if out is None:
            out = add_node(tree, "PARAM_N_Output", (NODE_GAP, 0))
            out.target = obj
        target_in = out.inputs["Geometrie"]
        src = source_of(target_in)
        join = src.node if src is not None and src.node.bl_idname == "PARAM_N_Join" else None
        if join is None:
            shift_right(tree, out.location.x)
            join = add_node(tree, "PARAM_N_Join", (out.location.x - NODE_GAP, out.location.y))
            if src is not None:
                tree.links.new(src, join.inputs["Geometrie"])
            tree.links.new(join.outputs["Geometrie"], target_in)
        lowest = min((n.location.y for n in tree.nodes), default=0)
        part_x = join.location.x - 2 * NODE_GAP
        sock = build_part(tree, kind, (part_x - NODE_GAP, lowest - 260), profile_mode)
        local = obj.matrix_world.inverted_safe() @ context.scene.cursor.location
        if local.length > 1e-6:
            move = add_node(tree, "PARAM_N_Transform", (part_x, lowest - 260))
            move.inputs["Verschieben"].default_value = tuple(local)
            tree.links.new(sock, move.inputs["Geometrie"])
            sock = move.outputs["Geometrie"]
        tree.links.new(sock, join.inputs["Geometrie"])
    scheduler.request(tree)
    return tree


def object_trees_using(tree):
    return [o for o in bpy.data.objects if o.param_tree == tree]


def frame_location(tree):
    xs = [n.location.x for n in tree.nodes] or [0]
    ys = [n.location.y for n in tree.nodes] or [0]
    return Vector((min(xs), min(ys)))
