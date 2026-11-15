# SPDX-License-Identifier: GPL-3.0-or-later
"""All nodes of the Parametric Tree."""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Matrix, Vector

from ..core import geometry, modifier_ops
from ..core.evaluator import (
    ANGLE, BOOL, FLOAT, GEOMETRY, INT, LENGTH, TREE_ID, VECTOR,
    MAX_GROUP_DEPTH, NodeError, evaluate_geometry,
)
from ..core.expressions import ExpressionError, evaluate as eval_expr
from .base import ParamNode, changed


# ---------------------------------------------------------------------------
# Parameters and inputs

class _ParameterNode(ParamNode):
    """Named value; visible in the side panel and usable by name in formulas."""

    param_unit = "NUMBER"

    param_name: StringProperty(name="Name", default="", update=changed)
    expose: BoolProperty(
        name="Exponieren",
        description="Als Eingang an Group-Nodes zeigen, die diesen Graph verwenden",
        default=False,
        update=changed,
    )

    def init(self, context):
        self.add_output(self.socket_type, "Wert")
        self.param_name = self._unique_name()

    def _unique_name(self):
        tree = self.id_data
        used = {getattr(n, "param_name", "") for n in tree.nodes if n != self}
        base = {"LENGTH": "laenge", "ANGLE": "winkel"}.get(self.param_unit, "wert")
        i = 1
        while f"{base}{i}" in used:
            i += 1
        return f"{base}{i}"

    def draw_props(self, context, layout):
        layout.prop(self, "param_name", text="")
        layout.prop(self, "value", text="")
        layout.prop(self, "expose")

    def parameter_value(self):
        return self.value

    def evaluate(self, ectx):
        return {"Wert": ectx.parameter_value(self)}


class PARAM_N_LengthParam(_ParameterNode, bpy.types.Node):
    bl_idname = "PARAM_N_LengthParam"
    bl_label = "Parameter Länge"
    bl_icon = "DRIVER_DISTANCE"
    param_unit = "LENGTH"
    socket_type = LENGTH
    value: FloatProperty(name="Wert", default=10.0, subtype="DISTANCE", unit="LENGTH", update=changed)


class PARAM_N_AngleParam(_ParameterNode, bpy.types.Node):
    bl_idname = "PARAM_N_AngleParam"
    bl_label = "Parameter Winkel"
    bl_icon = "DRIVER_ROTATIONAL_DIFFERENCE"
    param_unit = "ANGLE"
    socket_type = ANGLE
    value: FloatProperty(name="Wert", default=math.radians(45), subtype="ANGLE", update=changed)


class PARAM_N_NumberParam(_ParameterNode, bpy.types.Node):
    bl_idname = "PARAM_N_NumberParam"
    bl_label = "Parameter Zahl"
    bl_icon = "DRIVER"
    param_unit = "NUMBER"
    socket_type = FLOAT
    value: FloatProperty(name="Wert", default=1.0, update=changed)


class PARAM_N_Formula(ParamNode, bpy.types.Node):
    """Math expression with inputs a-d and every parameter name. Trigonometry uses degrees."""

    bl_idname = "PARAM_N_Formula"
    bl_label = "Formel"
    bl_icon = "EXPERIMENTAL"

    expression: StringProperty(name="Formel", default="a * 2", update=changed)
    result_type: EnumProperty(
        name="Ergebnis",
        items=[("LENGTH", "Länge", ""), ("ANGLE", "Winkel (Grad)", ""), ("NUMBER", "Zahl", "")],
        default="LENGTH",
        update=lambda self, ctx: self._retype(ctx),
    )

    def init(self, context):
        for n in "abcd":
            self.add_input(FLOAT, n, 0.0)
        self.add_output(LENGTH, "Ergebnis")

    def _retype(self, context):
        wanted = {"LENGTH": LENGTH, "ANGLE": ANGLE, "NUMBER": FLOAT}[self.result_type]
        out = self.outputs[0]
        if out.bl_idname != wanted:
            targets = [l.to_socket for l in out.links]
            self.outputs.remove(out)
            new = self.outputs.new(wanted, "Ergebnis")
            for t in targets:
                self.id_data.links.new(new, t)
        changed(self, context)

    def draw_props(self, context, layout):
        layout.prop(self, "expression", text="")
        layout.prop(self, "result_type", text="")

    def evaluate(self, ectx):
        names = dict(ectx.parameters)
        for n in "abcd":
            names[n] = ectx.get(self, n)
        try:
            value = eval_expr(self.expression, names)
        except ExpressionError as exc:
            raise NodeError(self, str(exc))
        if self.result_type == "ANGLE":
            value = math.radians(value)
        return {"Ergebnis": value}


class PARAM_N_Vector(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Vector"
    bl_label = "Vektor"
    bl_icon = "EMPTY_ARROWS"

    def init(self, context):
        self.add_input(LENGTH, "X", 0.0)
        self.add_input(LENGTH, "Y", 0.0)
        self.add_input(LENGTH, "Z", 0.0)
        self.add_output(VECTOR, "Vektor")

    def evaluate(self, ectx):
        return {"Vektor": (ectx.get(self, "X"), ectx.get(self, "Y"), ectx.get(self, "Z"))}


def _mesh_object_poll(self, obj):
    return obj.type == "MESH"


class PARAM_N_ObjectInput(ParamNode, bpy.types.Node):
    """Geometry of another object (link). Parametric objects stay linked live."""

    bl_idname = "PARAM_N_ObjectInput"
    bl_label = "Objekt-Eingang"
    bl_icon = "OBJECT_DATA"

    source: PointerProperty(name="Objekt", type=bpy.types.Object, poll=_mesh_object_poll, update=changed)
    relative: BoolProperty(
        name="Relative Lage",
        description="Lage des Objekts relativ zum Zielobjekt übernehmen",
        default=True,
        update=changed,
    )

    def init(self, context):
        self.add_output(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "source", text="")
        layout.prop(self, "relative")

    def evaluate(self, ectx):
        import bmesh
        if self.source is None:
            raise NodeError(self, "Kein Objekt gewählt")
        if self.source == ectx.owner:
            raise NodeError(self, "Ein Objekt kann sich nicht selbst als Eingang verwenden")
        bm = bmesh.new()
        bm.from_mesh(self.source.data)
        if self.relative:
            owner_matrix = ectx.owner.matrix_world if ectx.owner is not None else Matrix.Identity(4)
            geometry.transform(bm, owner_matrix.inverted_safe() @ self.source.matrix_world)
        return {"Geometrie": bm}


# ---------------------------------------------------------------------------
# Primitives

class PARAM_N_Box(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Box"
    bl_label = "Box"
    bl_icon = "MESH_CUBE"

    def init(self, context):
        self.add_input(LENGTH, "Breite", 20.0)
        self.add_input(LENGTH, "Tiefe", 20.0)
        self.add_input(LENGTH, "Höhe", 20.0)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        return {"Geometrie": geometry.box(ectx.get(self, "Breite"), ectx.get(self, "Tiefe"), ectx.get(self, "Höhe"))}


class PARAM_N_Cylinder(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Cylinder"
    bl_label = "Zylinder"
    bl_icon = "MESH_CYLINDER"

    def init(self, context):
        self.add_input(LENGTH, "Radius", 10.0)
        self.add_input(LENGTH, "Höhe", 20.0)
        self.add_input(INT, "Segmente", 48)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        return {"Geometrie": geometry.cylinder(ectx.get(self, "Radius"), ectx.get(self, "Höhe"), ectx.get(self, "Segmente"))}


class PARAM_N_Sphere(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Sphere"
    bl_label = "Kugel"
    bl_icon = "MESH_UVSPHERE"

    def init(self, context):
        self.add_input(LENGTH, "Radius", 10.0)
        self.add_input(INT, "Segmente", 48)
        self.add_input(INT, "Ringe", 24)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        return {"Geometrie": geometry.sphere(ectx.get(self, "Radius"), ectx.get(self, "Segmente"), ectx.get(self, "Ringe"))}


class PARAM_N_Cone(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Cone"
    bl_label = "Kegel"
    bl_icon = "MESH_CONE"

    def init(self, context):
        self.add_input(LENGTH, "Radius unten", 10.0)
        self.add_input(LENGTH, "Radius oben", 0.0)
        self.add_input(LENGTH, "Höhe", 20.0)
        self.add_input(INT, "Segmente", 48)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        return {"Geometrie": geometry.cone(
            ectx.get(self, "Radius unten"), ectx.get(self, "Radius oben"),
            ectx.get(self, "Höhe"), ectx.get(self, "Segmente"))}


# ---------------------------------------------------------------------------
# Profiles

class PARAM_N_Rectangle(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Rectangle"
    bl_label = "Rechteck-Profil"
    bl_icon = "MESH_PLANE"

    def init(self, context):
        self.add_input(LENGTH, "Breite", 30.0)
        self.add_input(LENGTH, "Höhe", 20.0)
        self.add_input(LENGTH, "Eckradius", 0.0)
        self.add_output(GEOMETRY, "Profil")

    def evaluate(self, ectx):
        pts = geometry.rectangle_points(ectx.get(self, "Breite"), ectx.get(self, "Höhe"), ectx.get(self, "Eckradius"))
        return {"Profil": geometry.profile_from_points(pts)}


class PARAM_N_Circle(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Circle"
    bl_label = "Kreis-Profil"
    bl_icon = "MESH_CIRCLE"

    def init(self, context):
        self.add_input(LENGTH, "Radius", 10.0)
        self.add_input(INT, "Segmente", 48)
        self.add_output(GEOMETRY, "Profil")

    def evaluate(self, ectx):
        return {"Profil": geometry.profile_from_points(geometry.circle_points(ectx.get(self, "Radius"), ectx.get(self, "Segmente")))}


class PARAM_N_Polygon(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Polygon"
    bl_label = "Polygon-Profil"
    bl_icon = "SEQ_CHROMA_SCOPE"

    def init(self, context):
        self.add_input(LENGTH, "Radius", 10.0)
        self.add_input(INT, "Ecken", 6)
        self.add_output(GEOMETRY, "Profil")

    def evaluate(self, ectx):
        return {"Profil": geometry.profile_from_points(geometry.polygon_points(ectx.get(self, "Radius"), ectx.get(self, "Ecken")))}


class PARAM_N_Polyline(ParamNode, bpy.types.Node):
    """Closed outline from a point list ``x, y; x, y; ...``. Values may use parameter names and formulas."""

    bl_idname = "PARAM_N_Polyline"
    bl_label = "Polylinie-Profil"
    bl_icon = "IPO_LINEAR"

    points: StringProperty(name="Punkte", default="0, 0; 30, 0; 30, 10; 10, 25; 0, 25", update=changed)

    def init(self, context):
        self.add_output(GEOMETRY, "Profil")

    def draw_props(self, context, layout):
        layout.prop(self, "points", text="")

    def evaluate(self, ectx):
        names = ectx.parameters
        pts = []
        for i, chunk in enumerate(p for p in self.points.split(";") if p.strip()):
            parts = [c for c in chunk.split(",")]
            if len(parts) != 2:
                raise NodeError(self, f"Punkt {i + 1}: bitte als 'x, y' angeben (Dezimalpunkt statt Komma)")
            try:
                pts.append((eval_expr(parts[0], names), eval_expr(parts[1], names)))
            except ExpressionError as exc:
                raise NodeError(self, f"Punkt {i + 1}: {exc}")
        return {"Profil": geometry.profile_from_points(pts)}


# ---------------------------------------------------------------------------
# Operations

class PARAM_N_Extrude(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Extrude"
    bl_label = "Extrudieren"
    bl_icon = "MOD_SOLIDIFY"

    def init(self, context):
        self.add_input(GEOMETRY, "Profil")
        self.add_input(LENGTH, "Höhe", 10.0)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Profil")
        return {"Geometrie": geometry.extrude(bm, ectx.get(self, "Höhe"))}


class PARAM_N_Revolve(ParamNode, bpy.types.Node):
    """Turns a profile around the Z axis. Profile X = distance from the axis, profile Y = height."""

    bl_idname = "PARAM_N_Revolve"
    bl_label = "Rotieren (Revolve)"
    bl_icon = "MOD_SCREW"

    def init(self, context):
        self.add_input(GEOMETRY, "Profil")
        self.add_input(ANGLE, "Winkel", math.radians(360))
        self.add_input(INT, "Segmente", 48)
        self.add_input(LENGTH, "Achsabstand", 20.0)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Profil")
        return {"Geometrie": geometry.revolve(bm, ectx.get(self, "Winkel"), ectx.get(self, "Segmente"), ectx.get(self, "Achsabstand"))}


class PARAM_N_Boolean(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Boolean"
    bl_label = "Boolean"
    bl_icon = "MOD_BOOLEAN"

    operation: EnumProperty(
        name="Operation",
        items=[
            ("DIFFERENCE", "Differenz", "B von A abziehen"),
            ("UNION", "Vereinigung", "A und B verschmelzen"),
            ("INTERSECT", "Schnitt", "Nur die Überlappung behalten"),
        ],
        default="DIFFERENCE",
        update=changed,
    )

    def init(self, context):
        self.add_input(GEOMETRY, "A")
        self.add_input(GEOMETRY, "B")
        self.add_output(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "operation", text="")

    def evaluate(self, ectx):
        a = ectx.geometry(self, "A")
        b = ectx.geometry(self, "B", required=False)
        if b is None:
            return {"Geometrie": a}
        result = modifier_ops.boolean(a, b, self.operation)
        a.free()
        b.free()
        return {"Geometrie": result}


class PARAM_N_Bevel(ParamNode, bpy.types.Node):
    """Rounds or chamfers edges. 1 segment = chamfer, more segments = rounding."""

    bl_idname = "PARAM_N_Bevel"
    bl_label = "Bevel / Fase"
    bl_icon = "MOD_BEVEL"

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(LENGTH, "Breite", 1.0)
        self.add_input(INT, "Segmente", 3)
        self.add_input(ANGLE, "Winkelgrenze", math.radians(30))
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        return {"Geometrie": geometry.bevel(bm, ectx.get(self, "Breite"), ectx.get(self, "Segmente"), ectx.get(self, "Winkelgrenze"))}


class PARAM_N_Shell(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Shell"
    bl_label = "Shell / Wandstärke"
    bl_icon = "MOD_SOLIDIFY"

    inward: BoolProperty(name="Nach innen", default=True, update=changed)

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(LENGTH, "Dicke", 2.0)
        self.add_output(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "inward")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        result = modifier_ops.shell(bm, ectx.get(self, "Dicke"), self.inward)
        bm.free()
        return {"Geometrie": result}


class PARAM_N_Mirror(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Mirror"
    bl_label = "Spiegeln"
    bl_icon = "MOD_MIRROR"

    axis: EnumProperty(name="Achse", items=[("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")], default="X", update=changed)
    keep_original: BoolProperty(name="Original behalten", default=True, update=changed)
    merge: BoolProperty(name="Verschmelzen", default=True, update=changed)

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_output(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "axis", expand=True)
        layout.prop(self, "keep_original")
        layout.prop(self, "merge")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        return {"Geometrie": geometry.mirror(bm, self.axis, self.merge, self.keep_original)}


class PARAM_N_Join(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Join"
    bl_label = "Zusammenfügen"
    bl_icon = "SELECT_EXTEND"

    def init(self, context):
        sock = self.add_input(GEOMETRY, "Geometrie")
        sock.link_limit = 4095
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        import bmesh
        out = bmesh.new()
        for bm in ectx.get_all(self, "Geometrie"):
            if bm is not None:
                geometry.join(out, bm)
        return {"Geometrie": geometry.finish(out)}


# ---------------------------------------------------------------------------
# Modifiers

class PARAM_N_Transform(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Transform"
    bl_label = "Verschieben / Rotieren / Skalieren"
    bl_icon = "ORIENTATION_GLOBAL"

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(VECTOR, "Verschieben", (0.0, 0.0, 0.0))
        self.add_input(VECTOR, "Rotieren (Grad)", (0.0, 0.0, 0.0))
        self.add_input(VECTOR, "Skalieren", (1.0, 1.0, 1.0))
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        rot = [math.radians(a) for a in ectx.get(self, "Rotieren (Grad)")]
        m = geometry.compose(ectx.get(self, "Verschieben"), rot, ectx.get(self, "Skalieren"))
        geometry.transform(bm, m)
        if m.determinant() < 0:
            import bmesh
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        return {"Geometrie": geometry.finish(bm)}


class PARAM_N_Smooth(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_Smooth"
    bl_label = "Soften / Smooth"
    bl_icon = "MOD_SUBSURF"

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(INT, "Stufe", 2)
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        result = modifier_ops.subdivide_smooth(bm, ectx.get(self, "Stufe"))
        bm.free()
        return {"Geometrie": result}


class PARAM_N_LinearArray(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_LinearArray"
    bl_label = "Lineares Array"
    bl_icon = "MOD_ARRAY"

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(INT, "Anzahl", 3)
        self.add_input(VECTOR, "Versatz", (30.0, 0.0, 0.0))
        self.add_output(GEOMETRY, "Geometrie")

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        return {"Geometrie": geometry.linear_array(bm, ectx.get(self, "Anzahl"), ectx.get(self, "Versatz"))}


class PARAM_N_RadialArray(ParamNode, bpy.types.Node):
    bl_idname = "PARAM_N_RadialArray"
    bl_label = "Radiales Array"
    bl_icon = "FORCE_VORTEX"

    axis: EnumProperty(name="Achse", items=[("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")], default="Z", update=changed)

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")
        self.add_input(INT, "Anzahl", 6)
        self.add_input(ANGLE, "Gesamtwinkel", math.radians(360))
        self.add_input(VECTOR, "Zentrum", (0.0, 0.0, 0.0))
        self.add_output(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "axis", expand=True)

    def evaluate(self, ectx):
        bm = ectx.geometry(self, "Geometrie")
        return {"Geometrie": geometry.radial_array(
            bm, ectx.get(self, "Anzahl"), self.axis, ectx.get(self, "Gesamtwinkel"), ectx.get(self, "Zentrum"))}


# ---------------------------------------------------------------------------
# Structure

def _subtree_poll(self, tree):
    return tree.bl_idname == TREE_ID and tree != self.id_data


def _subtree_changed(self, context):
    self.sync_sockets()
    changed(self, context)


_UNIT_SOCKET = {"LENGTH": LENGTH, "ANGLE": ANGLE, "NUMBER": FLOAT}


class PARAM_N_Group(ParamNode, bpy.types.Node):
    """Uses another Parametric Tree as a sub-graph. Exposed parameters become inputs."""

    bl_idname = "PARAM_N_Group"
    bl_label = "Gruppe"
    bl_icon = "NODETREE"

    subtree: PointerProperty(name="Graph", type=bpy.types.NodeTree, poll=_subtree_poll, update=_subtree_changed)

    def init(self, context):
        self.add_output(GEOMETRY, "Geometrie")

    def exposed(self):
        if self.subtree is None:
            return []
        return [n for n in self.subtree.nodes if getattr(n, "expose", False) and getattr(n, "param_name", "")]

    def sync_sockets(self):
        """Make the inputs match the exposed parameters of the sub-graph."""
        wanted = [(n.param_name, _UNIT_SOCKET[n.param_unit], n) for n in self.exposed()]
        names = [w[0] for w in wanted]
        for sock in list(self.inputs):
            match = next((w for w in wanted if w[0] == sock.name), None)
            if match is None or match[1] != sock.bl_idname:
                self.inputs.remove(sock)
        for name, stype, node in wanted:
            if name not in self.inputs:
                sock = self.inputs.new(stype, name)
                sock.default_value = node.value
        # keep the order of the sub-graph
        for index, name in enumerate(names):
            current = [s.name for s in self.inputs].index(name)
            if current != index:
                self.inputs.move(current, index)

    def draw_props(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "subtree", text="")
        row.operator("param.group_sync_sockets", text="", icon="FILE_REFRESH").node_name = self.name
        if self.subtree is not None:
            layout.operator("param.group_enter", text="Gruppe öffnen", icon="FULLSCREEN_ENTER").node_name = self.name

    def evaluate(self, ectx):
        if self.subtree is None:
            raise NodeError(self, "Kein Graph gewählt")
        if ectx.depth >= MAX_GROUP_DEPTH or self.subtree.name in ectx.visited:
            raise NodeError(self, "Gruppe enthält sich selbst")
        overrides = {}
        for node in self.exposed():
            sock = self.inputs.get(node.param_name)
            if sock is not None:
                overrides[node.param_name] = ectx.get_socket(sock)
        visited = set(ectx.visited) | {ectx.tree.name}
        try:
            bm, _ctx = evaluate_geometry(self.subtree, owner=ectx.owner, overrides=overrides,
                                         depth=ectx.depth + 1, visited=visited)
        except NodeError as exc:
            raise NodeError(self, f"{self.subtree.name} › {exc.node.label or exc.node.name}: {exc.message}")
        if bm is None:
            raise NodeError(self, "Der Graph hat keinen Output-Node")
        return {"Geometrie": bm}


class PARAM_N_Output(ParamNode, bpy.types.Node):
    """Writes the geometry into the mesh of the target object."""

    bl_idname = "PARAM_N_Output"
    bl_label = "Output"
    bl_icon = "OUTPUT"

    target: PointerProperty(name="Objekt", type=bpy.types.Object, poll=_mesh_object_poll, update=changed)
    sync_mode: EnumProperty(
        name="Sync",
        items=[
            ("LIVE", "Live", "Jede Änderung baut das Modell neu auf", "LINKED", 0),
            ("FROZEN", "Eingefroren", "Graph bleibt erhalten, das Mesh wird nicht mehr aktualisiert", "UNLINKED", 1),
        ],
        default="LIVE",
        update=changed,
    )

    def init(self, context):
        self.add_input(GEOMETRY, "Geometrie")

    def draw_props(self, context, layout):
        layout.prop(self, "target", text="")
        layout.prop(self, "sync_mode", expand=True)

    def evaluate(self, ectx):
        return {}


classes = (
    PARAM_N_LengthParam,
    PARAM_N_AngleParam,
    PARAM_N_NumberParam,
    PARAM_N_Formula,
    PARAM_N_Vector,
    PARAM_N_ObjectInput,
    PARAM_N_Box,
    PARAM_N_Cylinder,
    PARAM_N_Sphere,
    PARAM_N_Cone,
    PARAM_N_Rectangle,
    PARAM_N_Circle,
    PARAM_N_Polygon,
    PARAM_N_Polyline,
    PARAM_N_Extrude,
    PARAM_N_Revolve,
    PARAM_N_Boolean,
    PARAM_N_Bevel,
    PARAM_N_Shell,
    PARAM_N_Mirror,
    PARAM_N_Join,
    PARAM_N_Transform,
    PARAM_N_Smooth,
    PARAM_N_LinearArray,
    PARAM_N_RadialArray,
    PARAM_N_Group,
    PARAM_N_Output,
)

CATEGORIES = [
    ("Parameter", ["PARAM_N_LengthParam", "PARAM_N_AngleParam", "PARAM_N_NumberParam", "PARAM_N_Formula", "PARAM_N_Vector", "PARAM_N_ObjectInput"]),
    ("Grundkörper", ["PARAM_N_Box", "PARAM_N_Cylinder", "PARAM_N_Sphere", "PARAM_N_Cone"]),
    ("Kurven & Skizze", ["PARAM_N_Rectangle", "PARAM_N_Circle", "PARAM_N_Polygon", "PARAM_N_Polyline"]),
    ("Operationen", ["PARAM_N_Extrude", "PARAM_N_Revolve", "PARAM_N_Boolean", "PARAM_N_Bevel", "PARAM_N_Shell", "PARAM_N_Mirror", "PARAM_N_Join"]),
    ("Modifier", ["PARAM_N_Transform", "PARAM_N_Smooth", "PARAM_N_LinearArray", "PARAM_N_RadialArray"]),
    ("Struktur", ["PARAM_N_Group", "PARAM_N_Output"]),
]
