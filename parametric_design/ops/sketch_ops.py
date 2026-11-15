# SPDX-License-Identifier: GPL-3.0-or-later
"""Sketch operators: create, constrain, delete, and the interactive tool."""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from ..core import scheduler
from ..nodes.sketch import CONSTRAINT_ITEMS
from . import graph
from .sketch_session import SketchSession, pressure_snap

TOOL_ITEMS = [
    ("SELECT", "Auswahl", "Auswählen und Punkte ziehen"),
    ("LINE", "Linie", "Linienzug zeichnen; Klick auf den Startpunkt schließt die Kontur"),
    ("RECT", "Rechteck", "Rechteck über zwei Ecken"),
    ("CIRCLE", "Kreis", "Kreis: Mittelpunkt, dann Radius"),
    ("ARC", "Bogen", "Bogen: Mittelpunkt, Anfang, Ende (gegen den Uhrzeigersinn)"),
]

PICK_RADIUS_PX = 14

# The running interactive session (one at a time), read by the overlay.
runtime = {"session": None}


def active_sketch(context):
    """Sketch node of the active object: the active node if it is a sketch, else the first one."""
    obj = context.active_object
    if not graph.is_parametric(obj):
        return None
    tree = obj.param_tree
    node = tree.nodes.active
    if node is not None and node.bl_idname == "PARAM_N_Sketch":
        return node
    for node in tree.nodes:
        if node.bl_idname == "PARAM_N_Sketch":
            return node
    return None


def ensure_sketch(context):
    node = active_sketch(context)
    if node is not None:
        return node
    obj = context.active_object
    if graph.is_parametric(obj) and obj.select_get():
        graph.add_part_to(context, obj, "SKETCH")
    else:
        graph.create_object(context, "Param Skizze", lambda tree: graph.build_part(tree, "SKETCH", (0, 0)))
    obj = context.active_object
    node = next(n for n in obj.param_tree.nodes if n.bl_idname == "PARAM_N_Sketch" and not n.points)
    obj.param_tree.nodes.active = node
    return node


class _SketchOperator:
    @classmethod
    def poll(cls, context):
        if active_sketch(context) is None:
            cls.poll_message_set("Das aktive Objekt hat keine Skizze")
            return False
        return True


class PARAM_OT_sketch_add(bpy.types.Operator):
    """Add a sketch element by coordinates (the drawing tool does this for you)"""

    bl_idname = "param.sketch_add"
    bl_label = "Skizzenelement hinzufügen"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[("LINE", "Linie", ""), ("RECT", "Rechteck", ""), ("CIRCLE", "Kreis", ""), ("ARC", "Bogen", "")], default="RECT")
    x1: FloatProperty(name="X1", default=0.0)
    y1: FloatProperty(name="Y1", default=0.0)
    x2: FloatProperty(name="X2", default=30.0)
    y2: FloatProperty(name="Y2", default=20.0)
    x3: FloatProperty(name="X3", default=0.0)
    y3: FloatProperty(name="Y3", default=10.0)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        with scheduler.suspended():
            node = ensure_sketch(context)
            session = SketchSession(node, grid=0.0)
            session.tool = self.kind
            tiny = 1e-6
            session.press(self.x1, self.y1, tiny, False)
            session.press(self.x2, self.y2, tiny, False)
            if self.kind == "ARC":
                session.press(self.x3, self.y3, tiny, False)
            session.chain_first = session.chain_last = None
            session.anchor = None
        scheduler.request(node.id_data)
        scheduler.flush()
        return {"FINISHED"}


def _selection(node):
    return {
        "points": [i for i, p in enumerate(node.points) if p.select],
        "lines": [i for i, l in enumerate(node.lines) if l.select],
        "curves": [("CIRCLE", i) for i, c in enumerate(node.circles) if c.select] + [("ARC", i) for i, a in enumerate(node.arcs) if a.select],
    }


def _curve_radius(node, curve):
    kind, index = curve
    if kind == "CIRCLE":
        return node.circles[index].radius
    arc = node.arcs[index]
    c, s = node.points[arc.center], node.points[arc.start]
    return math.hypot(s.x - c.x, s.y - c.y)


def apply_constraint(node, kind):
    """Add constraints of ``kind`` for the current selection. Returns the number added or an error text."""
    sel = _selection(node)
    pts, lines, curves = sel["points"], sel["lines"], sel["curves"]
    ends = [(node.lines[i].a, node.lines[i].b) for i in lines]
    P = node.points
    before = len(node.constraints)

    def dist(a, b):
        return math.hypot(P[a].x - P[b].x, P[a].y - P[b].y)

    if kind in {"HORIZONTAL", "VERTICAL"}:
        pairs = list(ends) + ([tuple(pts)] if len(pts) == 2 else [])
        if not pairs:
            return "Wähle Linien oder zwei Punkte"
        for a, b in pairs:
            node.add_constraint(kind, (a, b))
    elif kind == "COINCIDENT":
        if len(pts) == 2 and not lines and not curves:
            node.add_constraint("COINCIDENT", pts)
        elif len(pts) == 1 and len(lines) == 1:
            node.add_constraint("POINT_ON_LINE", (pts[0],) + ends[0])
        elif len(pts) == 1 and len(curves) == 1:
            node.add_constraint("POINT_ON_CURVE", pts, curves[0])
        else:
            return "Wähle zwei Punkte, oder einen Punkt und eine Linie oder Kurve"
    elif kind == "DISTANCE":
        pairs = list(ends) + ([tuple(pts)] if len(pts) == 2 else [])
        if not pairs and not curves:
            return "Wähle Linien, zwei Punkte oder einen Kreis"
        for a, b in pairs:
            node.add_constraint("DISTANCE", (a, b), value=dist(a, b))
        for curve in curves:
            node.add_constraint("RADIUS", curve=curve, value=_curve_radius(node, curve))
    elif kind == "RADIUS":
        if not curves:
            return "Wähle einen Kreis oder Bogen"
        for curve in curves:
            node.add_constraint("RADIUS", curve=curve, value=_curve_radius(node, curve))
    elif kind in {"PARALLEL", "PERPENDICULAR", "EQUAL", "ANGLE"}:
        if len(lines) != 2:
            return "Wähle genau zwei Linien"
        refs = ends[0] + ends[1]
        value = 0.0
        if kind == "ANGLE":
            d1 = (P[refs[1]].x - P[refs[0]].x, P[refs[1]].y - P[refs[0]].y)
            d2 = (P[refs[3]].x - P[refs[2]].x, P[refs[3]].y - P[refs[2]].y)
            value = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
        node.add_constraint(kind, refs, value=value)
    elif kind in {"POINT_ON_LINE", "MIDPOINT"}:
        if len(pts) != 1 or len(lines) != 1:
            return "Wähle einen Punkt und eine Linie"
        node.add_constraint(kind, (pts[0],) + ends[0])
    elif kind == "TANGENT":
        if len(lines) != 1 or len(curves) != 1:
            return "Wähle eine Linie und einen Kreis oder Bogen"
        node.add_constraint("TANGENT", ends[0], curves[0])
    elif kind == "POINT_ON_CURVE":
        if len(pts) != 1 or len(curves) != 1:
            return "Wähle einen Punkt und einen Kreis oder Bogen"
        node.add_constraint("POINT_ON_CURVE", pts, curves[0])
    else:
        return f"Unbekannter Constraint {kind}"
    return len(node.constraints) - before


class PARAM_OT_sketch_constrain(_SketchOperator, bpy.types.Operator):
    """Add a constraint to the selected sketch elements"""

    bl_idname = "param.sketch_constrain"
    bl_label = "Constraint setzen"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=CONSTRAINT_ITEMS)

    @classmethod
    def description(cls, context, props):
        return next(i[2] for i in CONSTRAINT_ITEMS if i[0] == props.kind)

    def execute(self, context):
        node = active_sketch(context)
        with scheduler.suspended():
            result = apply_constraint(node, self.kind)
        if isinstance(result, str):
            self.report({"WARNING"}, result)
            return {"CANCELLED"}
        scheduler.request(node.id_data)
        scheduler.flush()
        if "Konflikt" in node.sketch_status:
            self.report({"WARNING"}, "Dieser Constraint widerspricht den anderen")
        return {"FINISHED"}


class PARAM_OT_sketch_fix(_SketchOperator, bpy.types.Operator):
    """Fix or release the selected points (for lines: their end points)"""

    bl_idname = "param.sketch_fix"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node = active_sketch(context)
        sel = _selection(node)
        indices = set(sel["points"])
        for i in sel["lines"]:
            indices.update((node.lines[i].a, node.lines[i].b))
        if not indices:
            self.report({"WARNING"}, "Wähle Punkte oder Linien")
            return {"CANCELLED"}
        target = not all(node.points[i].fixed for i in indices)
        for i in indices:
            node.points[i].fixed = target
        scheduler.request(node.id_data)
        scheduler.flush()
        return {"FINISHED"}


class PARAM_OT_sketch_construction(_SketchOperator, bpy.types.Operator):
    """Turn the selected elements into construction lines and back (they do not count for the profile)"""

    bl_idname = "param.sketch_construction"
    bl_label = "Hilfslinie"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node = active_sketch(context)
        items = [e for coll in (node.lines, node.circles, node.arcs) for e in coll if e.select]
        if not items:
            return {"CANCELLED"}
        target = not all(e.construction for e in items)
        for e in items:
            e.construction = target
        scheduler.request(node.id_data)
        scheduler.flush()
        return {"FINISHED"}


class PARAM_OT_sketch_delete(_SketchOperator, bpy.types.Operator):
    """Delete the selected sketch elements"""

    bl_idname = "param.sketch_delete"
    bl_label = "Skizzenelemente löschen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node = active_sketch(context)
        delete_selected(node)
        scheduler.request(node.id_data)
        scheduler.flush()
        return {"FINISHED"}


def delete_selected(node):
    with scheduler.suspended():
        for index in range(len(node.lines) - 1, -1, -1):
            if node.lines[index].select:
                node.lines.remove(index)
        node.remove_curves({i for i, c in enumerate(node.circles) if c.select}, {i for i, a in enumerate(node.arcs) if a.select})
        node.remove_points([i for i, p in enumerate(node.points) if p.select])
        node.remove_unused_points()


class PARAM_OT_sketch_constraint_remove(_SketchOperator, bpy.types.Operator):
    """Remove this constraint"""

    bl_idname = "param.sketch_constraint_remove"
    bl_label = "Constraint entfernen"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        node = active_sketch(context)
        if not 0 <= self.index < len(node.constraints):
            return {"CANCELLED"}
        node.constraints.remove(self.index)
        scheduler.request(node.id_data)
        scheduler.flush()
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Interactive tool

def _view_region(area):
    return next((r for r in area.regions if r.type == "WINDOW"), None)


def _inside(region, x, y):
    return region.x <= x < region.x + region.width and region.y <= y < region.y + region.height


def mouse_to_sketch(region, rv3d, obj, mx, my):
    """Mouse position (region pixels) -> sketch coordinates on the object's local XY plane."""
    origin = region_2d_to_origin_3d(region, rv3d, (mx, my))
    direction = region_2d_to_vector_3d(region, rv3d, (mx, my))
    matrix = obj.matrix_world
    plane_co = matrix.translation
    plane_no = (matrix.to_3x3() @ Vector((0, 0, 1))).normalized()
    hit = intersect_line_plane(origin, origin + direction, plane_co, plane_no)
    if hit is None:
        return None
    local = matrix.inverted_safe() @ hit
    return local.x, local.y


def pick_radius(region, rv3d, obj, x, y, ui_scale):
    """Pick radius in sketch units for PICK_RADIUS_PX pixels at (x, y)."""
    m = obj.matrix_world
    a = location_3d_to_region_2d(region, rv3d, m @ Vector((x, y, 0)))
    b = location_3d_to_region_2d(region, rv3d, m @ Vector((x + 1, y, 0)))
    c = location_3d_to_region_2d(region, rv3d, m @ Vector((x, y + 1, 0)))
    if a is None or b is None or c is None:
        return 1.0
    px_per_unit = max((b - a).length, (c - a).length, 1e-6)
    return PICK_RADIUS_PX * ui_scale / px_per_unit


class PARAM_OT_sketch_tool(bpy.types.Operator):
    """Draw and edit the sketch in the viewport. Esc ends a shape, Esc again leaves the tool"""

    bl_idname = "param.sketch_tool"
    bl_label = "Skizzen-Werkzeug"
    bl_options = {"REGISTER"}

    tool: EnumProperty(items=TOOL_ITEMS, default="LINE")

    @classmethod
    def description(cls, context, props):
        return next(i[2] for i in TOOL_ITEMS if i[0] == props.tool)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def invoke(self, context, event):
        wm = context.window_manager
        session = runtime["session"]
        if wm.param_sketch_running and session is not None and session.node is not None:
            # The tool is already running: only switch the mode.
            session.set_tool(self.tool)
            wm.param_sketch_tool = self.tool
            _redraw(context)
            return {"FINISHED"}
        area = context.area if context.area and context.area.type == "VIEW_3D" else None
        if area is None:
            area = next((a for a in context.screen.areas if a.type == "VIEW_3D"), None)
        if area is None:
            self.report({"ERROR"}, "Kein 3D-Viewport gefunden")
            return {"CANCELLED"}
        node = ensure_sketch(context)
        bpy.ops.ed.undo_push(message="Skizze beginnen")
        session = SketchSession(node, grid=context.scene.param_settings.sketch_grid)
        session.tool = self.tool
        runtime["session"] = session
        self._area = area
        self._object_name = context.active_object.name
        wm.param_sketch_tool = self.tool
        wm.param_sketch_running = True
        wm.modal_handler_add(self)
        context.workspace.status_text_set("Skizze: Klick = Punkt · Esc/Enter = Form beenden · Esc = Werkzeug verlassen · Entf = löschen · Stift fest drücken = Snap")
        _redraw(context)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def _finish(self, context):
        session = runtime["session"]
        if session is not None and session.node is not None:
            session.cancel()
            session.release()
            scheduler.request(session.node.id_data)
        runtime["session"] = None
        context.window_manager.param_sketch_running = False
        context.workspace.status_text_set(None)
        _redraw(context)
        return {"FINISHED"}

    def modal(self, context, event):
        wm = context.window_manager
        session = runtime["session"]
        obj = bpy.data.objects.get(self._object_name)
        if not wm.param_sketch_running or session is None or session.node is None or obj is None:
            return self._finish(context)
        try:
            region = _view_region(self._area)
        except ReferenceError:
            return self._finish(context)
        if region is None or context.mode != "OBJECT":
            return self._finish(context)

        if event.type == "ESC" and event.value == "PRESS":
            if session.cancel():
                scheduler.request(session.node.id_data)
                _redraw(context)
                return {"RUNNING_MODAL"}
            return self._finish(context)
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if session.cancel():
                scheduler.request(session.node.id_data)
            _redraw(context)
            return {"RUNNING_MODAL"}

        mx, my = event.mouse_x, event.mouse_y
        in_view = _inside(region, mx, my) and not any(
            r.type != "WINDOW" and r.width > 1 and _inside(r, mx, my) for r in self._area.regions)
        if not in_view and session.drag_point is None:
            return {"PASS_THROUGH"}

        rv3d = self._area.spaces.active.region_3d
        pos = mouse_to_sketch(region, rv3d, obj, mx - region.x, my - region.y)
        ts = context.scene.tool_settings
        toggle = ts.use_snap != event.ctrl
        snap_on = pressure_snap(event.pressure, event.is_tablet, toggle)
        ui_scale = context.preferences.system.ui_scale

        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            if pos is not None:
                radius = pick_radius(region, rv3d, obj, pos[0], pos[1], ui_scale)
                session.grid = context.scene.param_settings.sketch_grid
                session.move(pos[0], pos[1], radius, snap_on)
                self._area.tag_redraw()
            return {"PASS_THROUGH"} if session.drag_point is None else {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS" and pos is not None:
                radius = pick_radius(region, rv3d, obj, pos[0], pos[1], ui_scale)
                message = session.press(pos[0], pos[1], radius, snap_on, extend=event.shift)
                if message:
                    bpy.ops.ed.undo_push(message=message)
                _redraw(context)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE":
                message = session.release()
                if message:
                    bpy.ops.ed.undo_push(message=message)
                _redraw(context)
                return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}

        if event.type in {"DEL", "X", "BACK_SPACE"} and event.value == "PRESS" and not session.busy:
            delete_selected(session.node)
            scheduler.request(session.node.id_data)
            bpy.ops.ed.undo_push(message="Skizze: löschen")
            _redraw(context)
            return {"RUNNING_MODAL"}

        if event.type == "RIGHTMOUSE" and event.value == "PRESS" and session.busy:
            session.cancel()
            scheduler.request(session.node.id_data)
            _redraw(context)
            return {"RUNNING_MODAL"}

        # Everything else (view navigation, undo, shortcuts) goes to Blender.
        return {"PASS_THROUGH"}


class PARAM_OT_sketch_stop(bpy.types.Operator):
    """Leave the sketch tool"""

    bl_idname = "param.sketch_stop"
    bl_label = "Skizze beenden"

    def execute(self, context):
        context.window_manager.param_sketch_running = False
        _redraw(context)
        return {"FINISHED"}


def _redraw(context):
    wm = context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "NODE_EDITOR"}:
                area.tag_redraw()


classes = (
    PARAM_OT_sketch_add,
    PARAM_OT_sketch_constrain,
    PARAM_OT_sketch_fix,
    PARAM_OT_sketch_construction,
    PARAM_OT_sketch_delete,
    PARAM_OT_sketch_constraint_remove,
    PARAM_OT_sketch_tool,
    PARAM_OT_sketch_stop,
)


def register_props():
    bpy.types.WindowManager.param_sketch_running = BoolProperty(default=False, options={"SKIP_SAVE"})
    bpy.types.WindowManager.param_sketch_tool = EnumProperty(items=TOOL_ITEMS, default="SELECT", options={"SKIP_SAVE"})


def unregister_props():
    del bpy.types.WindowManager.param_sketch_tool
    del bpy.types.WindowManager.param_sketch_running
