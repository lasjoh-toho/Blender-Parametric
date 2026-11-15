# SPDX-License-Identifier: GPL-3.0-or-later
"""Sketch node: points, lines, circles and arcs held together by constraints."""

import math

import bmesh
import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, StringProperty,
)

from ..core import geometry, sketch_solver
from ..core.evaluator import GEOMETRY, INT, NodeError
from ..core.expressions import ExpressionError, evaluate as eval_expr
from .base import ParamNode

CONSTRAINT_ITEMS = [
    ("COINCIDENT", "Deckungsgleich", "Zwei Punkte liegen aufeinander"),
    ("HORIZONTAL", "Horizontal", "Zwei Punkte liegen auf gleicher Höhe"),
    ("VERTICAL", "Vertikal", "Zwei Punkte liegen übereinander"),
    ("DISTANCE", "Distanz", "Abstand zweier Punkte bzw. Länge einer Linie"),
    ("PARALLEL", "Parallel", "Zwei Linien sind parallel"),
    ("PERPENDICULAR", "Senkrecht", "Zwei Linien stehen senkrecht aufeinander"),
    ("EQUAL", "Gleich", "Zwei Linien sind gleich lang"),
    ("ANGLE", "Winkel", "Winkel zwischen zwei Linien"),
    ("POINT_ON_LINE", "Kolinear", "Ein Punkt liegt auf einer Linie"),
    ("MIDPOINT", "Mittelpunkt", "Ein Punkt liegt in der Mitte einer Linie"),
    ("RADIUS", "Radius", "Radius eines Kreises oder Bogens"),
    ("TANGENT", "Tangente", "Eine Linie berührt einen Kreis oder Bogen"),
    ("POINT_ON_CURVE", "Punkt auf Kurve", "Ein Punkt liegt auf einem Kreis oder Bogen"),
]
CONSTRAINT_LABELS = {i[0]: i[1] for i in CONSTRAINT_ITEMS}

# Runtime-only state, keyed by (tree name, node name): point index -> target while dragging.
drag_targets = {}


class PARAM_PG_sketch_point(bpy.types.PropertyGroup):
    x: FloatProperty()
    y: FloatProperty()
    fixed: BoolProperty(name="Fix", description="Der Punkt bleibt, wo er ist")
    select: BoolProperty()


class PARAM_PG_sketch_line(bpy.types.PropertyGroup):
    a: IntProperty()
    b: IntProperty()
    construction: BoolProperty(name="Hilfslinie", description="Zählt nicht zum Profil")
    select: BoolProperty()


class PARAM_PG_sketch_circle(bpy.types.PropertyGroup):
    center: IntProperty()
    radius: FloatProperty(default=10.0)
    construction: BoolProperty(name="Hilfslinie")
    select: BoolProperty()


class PARAM_PG_sketch_arc(bpy.types.PropertyGroup):
    """Counter-clockwise from start to end around the centre."""

    center: IntProperty()
    start: IntProperty()
    end: IntProperty()
    construction: BoolProperty(name="Hilfslinie")
    select: BoolProperty()


def _constraint_changed(self, context):
    from ..core import scheduler
    scheduler.request(self.id_data)


class PARAM_PG_sketch_constraint(bpy.types.PropertyGroup):
    kind: EnumProperty(items=CONSTRAINT_ITEMS)
    p1: IntProperty(default=-1)
    p2: IntProperty(default=-1)
    p3: IntProperty(default=-1)
    p4: IntProperty(default=-1)
    curve_kind: EnumProperty(items=[("NONE", "", ""), ("CIRCLE", "Kreis", ""), ("ARC", "Bogen", "")], default="NONE")
    curve: IntProperty(default=-1)
    value: FloatProperty(name="Wert", update=_constraint_changed, precision=3)
    value_length: FloatProperty(
        name="Wert", subtype="DISTANCE", unit="LENGTH", precision=3,
        get=lambda self: self.value, set=lambda self, v: setattr(self, "value", v))
    value_angle: FloatProperty(
        name="Wert", subtype="ANGLE", unit="ROTATION",
        get=lambda self: self.value, set=lambda self, v: setattr(self, "value", v))
    expression: StringProperty(
        name="Formel",
        description="Optional: Parameter-Name oder Formel statt eines festen Werts, z. B. breite / 2 (Winkel in Grad)",
        update=_constraint_changed,
    )

    def point_refs(self):
        n = sketch_solver.KINDS[self.kind][0]
        return (self.p1, self.p2, self.p3, self.p4)[:n]

    @property
    def has_value(self):
        return sketch_solver.KINDS[self.kind][2]


class PARAM_N_Sketch(ParamNode, bpy.types.Node):
    """Free sketch in the XY plane. Closed outlines become the profile."""

    bl_idname = "PARAM_N_Sketch"
    bl_label = "Skizze"
    bl_icon = "GREASEPENCIL"

    points: CollectionProperty(type=PARAM_PG_sketch_point)
    lines: CollectionProperty(type=PARAM_PG_sketch_line)
    circles: CollectionProperty(type=PARAM_PG_sketch_circle)
    arcs: CollectionProperty(type=PARAM_PG_sketch_arc)
    constraints: CollectionProperty(type=PARAM_PG_sketch_constraint)
    sketch_status: StringProperty(default="Leer")
    sketch_dof: IntProperty(default=0)

    def init(self, context):
        self.add_input(INT, "Kreissegmente", 48)
        self.add_output(GEOMETRY, "Profil")

    def draw_props(self, context, layout):
        layout.label(text=f"{len(self.lines)} Linien · {len(self.circles) + len(self.arcs)} Kurven · {len(self.constraints)} Constraints")
        layout.label(text=self.sketch_status, icon="CHECKMARK" if self.sketch_dof == 0 and "Konflikt" not in self.sketch_status else "INFO")

    # -- editing helpers (used by the operators) ----------------------------
    def add_point(self, x, y, fixed=False):
        p = self.points.add()
        p.x, p.y, p.fixed = x, y, fixed
        return len(self.points) - 1

    def add_line(self, a, b, construction=False):
        line = self.lines.add()
        line.a, line.b, line.construction = a, b, construction
        return len(self.lines) - 1

    def add_circle(self, center, radius):
        c = self.circles.add()
        c.center, c.radius = center, radius
        return len(self.circles) - 1

    def add_arc(self, center, start, end):
        arc = self.arcs.add()
        arc.center, arc.start, arc.end = center, start, end
        return len(self.arcs) - 1

    def add_constraint(self, kind, points=(), curve=None, value=0.0, expression=""):
        if not sketch_solver.KINDS[kind][2]:
            # the same geometric constraint twice would only clutter the list
            wanted = (kind, tuple(points), tuple(curve) if curve is not None else ("NONE", -1))
            for con in self.constraints:
                if (con.kind, tuple(con.point_refs()), (con.curve_kind, con.curve)) == wanted:
                    return con
        con = self.constraints.add()
        con.kind = kind
        for name, index in zip(("p1", "p2", "p3", "p4"), points):
            setattr(con, name, index)
        if curve is not None:
            con.curve_kind, con.curve = curve
        con.value = float(value)
        if expression:
            con.expression = expression
        return con

    def remove_points(self, indices):
        """Remove points together with everything that uses them, then renumber."""
        doomed = set(indices)
        if not doomed:
            return
        self._remove_where(self.lines, lambda l: l.a in doomed or l.b in doomed)
        dead_circles = {i for i, c in enumerate(self.circles) if c.center in doomed}
        dead_arcs = {i for i, a in enumerate(self.arcs) if {a.center, a.start, a.end} & doomed}
        self.remove_curves(dead_circles, dead_arcs)
        self._remove_where(self.constraints, lambda c: any(i in doomed for i in c.point_refs()))
        remap = {}
        new = 0
        for old in range(len(self.points)):
            if old not in doomed:
                remap[old] = new
                new += 1
        for index in sorted(doomed, reverse=True):
            self.points.remove(index)
        for line in self.lines:
            line.a, line.b = remap[line.a], remap[line.b]
        for c in self.circles:
            c.center = remap[c.center]
        for arc in self.arcs:
            arc.center, arc.start, arc.end = remap[arc.center], remap[arc.start], remap[arc.end]
        for con in self.constraints:
            for name in ("p1", "p2", "p3", "p4")[: len(con.point_refs())]:
                setattr(con, name, remap[getattr(con, name)])

    def remove_curves(self, circle_indices=(), arc_indices=()):
        for kind, coll, dead in (("CIRCLE", self.circles, set(circle_indices)), ("ARC", self.arcs, set(arc_indices))):
            if not dead:
                continue
            self._remove_where(self.constraints, lambda c, k=kind, d=dead: c.curve_kind == k and c.curve in d)
            remap = {}
            new = 0
            for old in range(len(coll)):
                if old not in dead:
                    remap[old] = new
                    new += 1
            for index in sorted(dead, reverse=True):
                coll.remove(index)
            for con in self.constraints:
                if con.curve_kind == kind:
                    con.curve = remap[con.curve]

    @staticmethod
    def _remove_where(collection, predicate):
        for index in range(len(collection) - 1, -1, -1):
            if predicate(collection[index]):
                collection.remove(index)

    def remove_unused_points(self):
        used = set()
        for line in self.lines:
            used.update((line.a, line.b))
        for c in self.circles:
            used.add(c.center)
        for arc in self.arcs:
            used.update((arc.center, arc.start, arc.end))
        self.remove_points([i for i in range(len(self.points)) if i not in used])

    def clear_selection(self):
        for coll in (self.points, self.lines, self.circles, self.arcs):
            for item in coll:
                if item.select:
                    item.select = False

    # -- solving ------------------------------------------------------------
    def _runtime_key(self):
        return (self.id_data.name, self.name)

    def solver_constraints(self, names):
        out = []
        for con in self.constraints:
            value = con.value
            if con.has_value and con.expression.strip():
                value = eval_expr(con.expression, names)
                if con.kind == "ANGLE":
                    value = math.radians(value)
            curve = (con.curve_kind, con.curve) if con.curve_kind != "NONE" else None
            out.append(sketch_solver.Constraint(con.kind, con.point_refs(), curve, value))
        return out

    def solve(self, names=None, store=True):
        points = [(p.x, p.y) for p in self.points]
        fixed = {i for i, p in enumerate(self.points) if p.fixed}
        circles = [(c.center, c.radius) for c in self.circles]
        arcs = [(a.center, a.start, a.end) for a in self.arcs]
        drag = drag_targets.get(self._runtime_key())
        result = sketch_solver.solve(points, self.solver_constraints(names or {}), fixed, circles, arcs, drag)
        if store and (result.converged or drag):
            for p, (x, y) in zip(self.points, result.points):
                if abs(p.x - x) > 1e-9 or abs(p.y - y) > 1e-9:
                    p.x, p.y = float(x), float(y)
            for c, r in zip(self.circles, result.radii):
                if abs(c.radius - r) > 1e-9:
                    c.radius = float(r)
        if not self.points:
            status = "Leer"
        elif result.status == "CONFLICT":
            status = "Konflikt: Constraints widersprechen sich"
        elif result.dof == 0:
            status = "Voll bestimmt"
        else:
            status = f"{result.dof} Freiheitsgrad{'e' if result.dof != 1 else ''} offen"
        if self.sketch_status != status:
            self.sketch_status = status
        if self.sketch_dof != result.dof:
            self.sketch_dof = result.dof
        return result

    def arc_points(self, arc, segments):
        c = self.points[arc.center]
        s = self.points[arc.start]
        e = self.points[arc.end]
        radius = math.hypot(s.x - c.x, s.y - c.y)
        a0 = math.atan2(s.y - c.y, s.x - c.x)
        a1 = math.atan2(e.y - c.y, e.x - c.x)
        sweep = (a1 - a0) % (2 * math.pi)
        if sweep < 1e-9:
            sweep = 2 * math.pi
        steps = max(2, int(math.ceil(segments * sweep / (2 * math.pi))))
        pts = [(c.x + radius * math.cos(a0 + sweep * i / steps), c.y + radius * math.sin(a0 + sweep * i / steps)) for i in range(1, steps)]
        return pts

    def build_profile(self, segments):
        """Faces from all closed outlines (inner outlines become holes)."""
        segments = max(8, int(segments))
        bm = bmesh.new()
        verts = {}

        def vert(index):
            if index not in verts:
                p = self.points[index]
                verts[index] = bm.verts.new((p.x, p.y, 0.0))
            return verts[index]

        def edge(v1, v2):
            if v1 is not v2 and bm.edges.get((v1, v2)) is None:
                bm.edges.new((v1, v2))

        for line in self.lines:
            if not line.construction:
                edge(vert(line.a), vert(line.b))
        for arc in self.arcs:
            if arc.construction:
                continue
            chain = [vert(arc.start)] + [bm.verts.new((x, y, 0.0)) for x, y in self.arc_points(arc, segments)] + [vert(arc.end)]
            for v1, v2 in zip(chain, chain[1:]):
                edge(v1, v2)
        for circle in self.circles:
            if circle.construction or circle.radius <= 1e-9:
                continue
            c = self.points[circle.center]
            ring = [bm.verts.new((c.x + circle.radius * math.cos(2 * math.pi * i / segments),
                                  c.y + circle.radius * math.sin(2 * math.pi * i / segments), 0.0)) for i in range(segments)]
            for i in range(segments):
                edge(ring[i], ring[(i + 1) % segments])
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
        # Open ends cannot bound a face: peel them away.
        while True:
            dangling = [v for v in bm.verts if len(v.link_edges) < 2]
            if not dangling:
                break
            bmesh.ops.delete(bm, geom=dangling, context="VERTS")
        if not bm.edges:
            return bm  # nothing closed yet: an empty profile, not an error
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=True, edges=bm.edges[:], normal=(0.0, 0.0, 1.0))
        if not bm.faces:
            bm.free()
            raise NodeError(self, "Die Kontur ließ sich nicht füllen (überschneidet sie sich?)")
        geometry.finish(bm)
        for face in bm.faces:
            if face.normal.z < 0:
                face.normal_flip()
        bm.normal_update()
        return bm

    def evaluate(self, ectx):
        try:
            result = self.solve(ectx.parameters)
        except ExpressionError as exc:
            raise NodeError(self, f"Constraint-Formel: {exc}")
        if result.status == "CONFLICT":
            raise NodeError(self, "Constraints widersprechen sich")
        return {"Profil": self.build_profile(ectx.get(self, "Kreissegmente"))}


classes = (
    PARAM_PG_sketch_point,
    PARAM_PG_sketch_line,
    PARAM_PG_sketch_circle,
    PARAM_PG_sketch_arc,
    PARAM_PG_sketch_constraint,
    PARAM_N_Sketch,
)
