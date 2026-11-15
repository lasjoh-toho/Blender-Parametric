# SPDX-License-Identifier: GPL-3.0-or-later
"""Evaluation of a Parametric Tree."""

import math
import time

import bmesh

from . import geometry
from .expressions import ExpressionError
from .geometry import GeometryError

TREE_ID = "PARAM_NT_tree"

GEOMETRY = "PARAM_SocketGeometry"
LENGTH = "PARAM_SocketLength"
ANGLE = "PARAM_SocketAngle"
FLOAT = "PARAM_SocketFloat"
INT = "PARAM_SocketInt"
BOOL = "PARAM_SocketBool"
VECTOR = "PARAM_SocketVector"

NUMERIC = {LENGTH, ANGLE, FLOAT, INT, BOOL}

MAX_GROUP_DEPTH = 16

# Set while a tree is being evaluated so update callbacks triggered by the
# evaluation itself (e.g. node colours) do not schedule new evaluations.
state = {"evaluating": 0}


class NodeError(Exception):
    def __init__(self, node, message):
        super().__init__(message)
        self.node = node
        self.message = message


class EvalContext:
    def __init__(self, tree, owner=None, overrides=None, depth=0, visited=None):
        self.tree = tree
        self.owner = owner  # object the result is written to (may be None)
        self.overrides = overrides or {}
        self.depth = depth
        self.visited = visited or set()
        self.memo = {}
        self.active = set()
        self.errors = []
        self._parameters = None

    # -- parameters ---------------------------------------------------------
    @property
    def parameters(self):
        """Mapping of parameter name -> value as seen by formulas (angles in degrees)."""
        if self._parameters is None:
            self._parameters = {}
            for node in self.tree.nodes:
                name = getattr(node, "param_name", "")
                if not name or not hasattr(node, "parameter_value"):
                    continue
                value = self.parameter_value(node)
                if getattr(node, "param_unit", "") == "ANGLE":
                    value = math.degrees(value)
                self._parameters[name] = value
        return self._parameters

    def parameter_value(self, node):
        if node.param_name in self.overrides:
            return self.overrides[node.param_name]
        return node.parameter_value()

    # -- node evaluation ----------------------------------------------------
    def outputs_of(self, node):
        key = node.name
        if key in self.memo:
            return self.memo[key]
        if key in self.active:
            raise NodeError(node, "Kreis im Graph")
        self.active.add(key)
        try:
            try:
                result = node.evaluate(self)
            except NodeError:
                raise
            except (GeometryError, ExpressionError, ValueError, TypeError, ZeroDivisionError, RuntimeError) as exc:
                raise NodeError(node, str(exc))
        finally:
            self.active.discard(key)
        if not isinstance(result, dict):
            result = {node.outputs[0].identifier: result} if node.outputs else {}
        self.memo[key] = result
        return result

    def _source(self, socket):
        """Follow a link backwards through reroutes; return (from_socket) or None."""
        links = [l for l in socket.links if not l.is_muted and l.is_valid] if socket.is_linked else []
        if not links:
            return None
        from_socket = links[0].from_socket
        seen = 0
        while from_socket.node.bl_idname == "NodeReroute":
            seen += 1
            inp = from_socket.node.inputs[0]
            nxt = [l for l in inp.links if not l.is_muted] if inp.is_linked else []
            if not nxt or seen > 64:
                return None
            from_socket = nxt[0].from_socket
        return from_socket

    def _value_from(self, from_socket):
        node = from_socket.node
        if getattr(node, "mute", False):
            # A muted node passes its first geometry input through.
            for inp in node.inputs:
                if inp.bl_idname == GEOMETRY:
                    return self.get_socket(inp)
            raise NodeError(node, "Node ist stummgeschaltet")
        outs = self.outputs_of(node)
        if from_socket.identifier not in outs:
            raise NodeError(node, f"Ausgang {from_socket.name} liefert keinen Wert")
        return outs[from_socket.identifier]

    def get_socket(self, socket):
        src = self._source(socket)
        if src is None:
            if socket.bl_idname == GEOMETRY:
                return None
            return _plain(socket.default_value, socket.bl_idname)
        value = self._value_from(src)
        return convert(value, src.bl_idname, socket.bl_idname, socket.node)

    def get(self, node, name):
        socket = node.inputs.get(name)
        if socket is None:
            raise NodeError(node, f"Eingang {name} fehlt")
        return self.get_socket(socket)

    def get_all(self, node, name):
        """All values linked into a multi-input socket (in link order)."""
        socket = node.inputs[name]
        values = []
        for link in sorted(socket.links, key=lambda l: getattr(l, "multi_input_sort_id", 0)):
            if link.is_muted or not link.is_valid:
                continue
            src = link.from_socket
            hops = 0
            while src.node.bl_idname == "NodeReroute" and src.node.inputs[0].is_linked and hops < 64:
                src = src.node.inputs[0].links[0].from_socket
                hops += 1
            if src.node.bl_idname == "NodeReroute":
                continue
            values.append(convert(self._value_from(src), src.bl_idname, socket.bl_idname, node))
        return values

    def geometry(self, node, name, required=True):
        """Geometry input as a private copy the caller may modify."""
        bm = self.get(node, name)
        if bm is None:
            if required:
                raise NodeError(node, f"Eingang {name} ist nicht verbunden")
            return None
        return bm.copy()


def _plain(value, socket_type):
    if socket_type == VECTOR:
        return tuple(value)
    if socket_type == INT:
        return int(value)
    if socket_type == BOOL:
        return bool(value)
    return float(value)


def convert(value, from_type, to_type, node):
    if to_type == GEOMETRY or from_type == GEOMETRY:
        if to_type != from_type:
            raise NodeError(node, "Geometrie und Zahlen lassen sich nicht verbinden")
        return value
    if to_type == VECTOR:
        if from_type == VECTOR:
            return tuple(value)
        v = float(value)
        if from_type == ANGLE:
            v = math.degrees(v)
        return (v, v, v)
    if from_type == VECTOR:
        value = value[0]
        from_type = FLOAT
    v = float(value)
    # Angles are radians inside, degrees for everything a person types.
    if to_type == ANGLE and from_type != ANGLE:
        v = math.radians(v)
    elif from_type == ANGLE and to_type != ANGLE:
        v = math.degrees(v)
    if to_type == INT:
        return int(round(v))
    if to_type == BOOL:
        return bool(v)
    return v


# ---------------------------------------------------------------------------

def output_nodes(tree):
    return [n for n in tree.nodes if n.bl_idname == "PARAM_N_Output"]


def evaluate_geometry(tree, output_node=None, owner=None, overrides=None, depth=0, visited=None):
    """Evaluate ``tree`` and return (bmesh or None, EvalContext)."""
    ctx = EvalContext(tree, owner=owner, overrides=overrides, depth=depth, visited=visited)
    if output_node is None:
        outs = output_nodes(tree)
        if not outs:
            return None, ctx
        output_node = outs[0]
    bm = ctx.get(output_node, "Geometrie")
    return bm, ctx


def _mark(tree, error_node=None, message=""):
    for node in tree.nodes:
        if not hasattr(node, "param_error"):
            continue
        new_error = message if node == error_node else ""
        if node.param_error != new_error:
            node.param_error = new_error
        if node.param_dirty:
            node.param_dirty = False
        want_color = bool(new_error)
        if node.use_custom_color != want_color:
            node.use_custom_color = want_color
        if want_color:
            node.color = (0.55, 0.12, 0.1)


def write_mesh(obj, bm):
    me = obj.data
    bm.to_mesh(me)
    me.update()
    obj.update_tag()


def evaluate_tree(tree, force=False):
    """Evaluate every output of ``tree`` and write the results.

    Live outputs are always written; frozen ones only when ``force`` is True.
    Returns a list of objects that were updated.
    """
    updated = []
    state["evaluating"] += 1
    try:
        t0 = time.perf_counter()
        error = None
        for out in output_nodes(tree):
            if out.mute:
                continue
            target = out.target
            if not force and out.sync_mode != "LIVE":
                continue
            try:
                bm, _ctx = evaluate_geometry(tree, out, owner=target)
            except NodeError as exc:
                error = exc
                break
            if target is None or target.type != "MESH":
                if bm is not None:
                    bm.free()
                continue
            if bm is None:
                bm = bmesh.new()
            write_mesh(target, bm)
            bm.free()
            updated.append(target)
        if error is not None:
            _mark(tree, error.node if error.node.id_data == tree else None, error.message)
            if error.node.id_data != tree:
                tree.param_status = f"Fehler in Gruppe {error.node.id_data.name}: {error.message}"
            else:
                tree.param_status = f"Fehler in {error.node.label or error.node.name}: {error.message}"
        else:
            _mark(tree)
            tree.param_status = f"Aktuell ({(time.perf_counter() - t0) * 1000:.0f} ms)"
        tree.param_dirty = False
    finally:
        state["evaluating"] -= 1
    return updated
