# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from ..core import evaluator
from ..core.evaluator import TREE_ID
from ..nodes import sketch as sketch_nodes
from ..nodes import nodes as node_types
from ..ops import graph, printing, proportion, sketch_ops
from . import icons

CATEGORY = "Parametric"
COLUMNS = 4


def _active_tree(context):
    space = context.space_data
    if space is not None and space.type == "NODE_EDITOR":
        tree = space.edit_tree
        if tree is not None and tree.bl_idname == TREE_ID:
            return tree
    obj = context.active_object
    if graph.is_parametric(obj):
        return obj.param_tree
    return None


def _cell_units(context, columns):
    """Width of one grid cell in UI units (1 unit = height of a normal button)."""
    region = context.region
    ui_scale = context.preferences.system.ui_scale or 1.0
    unit = 20.0 * ui_scale
    width = (region.width if region is not None else 240 * ui_scale) - 44 * ui_scale  # tabs, scrollbar, margins
    gap = 0.1  # space between two tiles
    return max(2.0, min(6.0, (width / unit - gap * (columns - 1)) / columns))


def tool_grid(layout, context, tools, columns=COLUMNS):
    """Square tiles: a large two-colour icon with the tool button right below it.

    ``tools`` is a list of (operator, properties, label, icon name[, active]). Blender
    draws icons on buttons at a fixed 16 px, so the large icon is a separate
    element and the button under it carries the label.
    """
    units = _cell_units(context, columns)
    icon_scale = max(1.6, units - 1.0)
    col = layout.column(align=False)
    for start in range(0, len(tools), columns):
        row = col.row(align=True)
        row.alignment = "LEFT"
        for index, tool in enumerate(tools[start:start + columns]):
            idname, props, label, icon = tool[:4]
            active = len(tool) > 4 and tool[4]
            if index:
                gap = row.column()
                gap.ui_units_x = 0.1
                gap.label(text="")
            cell = row.column(align=True)
            cell.ui_units_x = units  # fixed width, so a lone tile in a row stays square
            tile = cell.box()
            pad = tile.row()
            pad.alignment = "CENTER"
            pad.template_icon(icon_value=icons.get(icon), scale=icon_scale)
            button = cell.row(align=True)
            button.scale_y = 1.1
            op = button.operator(idname, text=label, depress=active)
            for key, value in props.items():
                setattr(op, key, value)


# ---------------------------------------------------------------------------
# shared drawing

def draw_parameters(context, layout):
    tree = _active_tree(context)
    if tree is None:
        layout.label(text="Kein parametrisches Objekt aktiv", icon="INFO")
        return
    params = [n for n in tree.nodes if getattr(n, "param_name", "") and hasattr(n, "parameter_value")]
    col = layout.column(align=True)
    if not params:
        col.label(text="Noch keine benannten Parameter")
    scene = context.scene
    for node in params:
        lo, hi = node_types.parameter_limits(node, scene)
        linked = node_types.proportion_of(tree, node) is not None
        row = col.row(align=True)
        row.prop(node, "pick", text="", icon="LINKED" if linked else "NONE")
        field = row.row(align=True)
        field.enabled = not node.locked
        field.alert = (lo is not None and node.value < lo - 1e-9) or (hi is not None and node.value > hi + 1e-9)
        field.prop(node, "value", text=node.param_name)
        row.prop(node, "locked", text="", icon="LOCKED" if node.locked else "UNLOCKED")
        row.operator("param.parameter_settings", text="", icon="PREFERENCES").node_name = node.name
    if tree.param_notice:
        row = layout.row()
        row.alert = True
        row.label(text=tree.param_notice, icon="INFO")
    if len(params) >= 2:
        row = layout.row(align=True)
        row.operator("param.proportion_lock", text="Verhältnis", icon="LINKED").kind = "RATIO"
        row.operator("param.proportion_lock", text="Differenz", icon="DRIVER_DISTANCE").kind = "DIFFERENCE"
    for index, group in enumerate(tree.param_proportions):
        row = layout.row(align=True)
        row.label(text=proportion.describe(tree, group), icon="LINKED")
        row.operator("param.proportion_unlock", text="", icon="X").index = index
    row = layout.row(align=True)
    row.scale_y = 1.6
    row.operator("param.add_parameter", text="Länge", icon_value=icons.get("param_length")).unit = "LENGTH"
    row.operator("param.add_parameter", text="Winkel", icon_value=icons.get("param_angle")).unit = "ANGLE"
    row.operator("param.add_parameter", text="Zahl", icon_value=icons.get("param_number")).unit = "NUMBER"

    node = tree.nodes.active
    if node is None or not hasattr(node, "param_error") or not node.inputs:
        return
    box = layout.box()
    box.label(text=f"Werte: {node.label or node.bl_label}", icon="NODE")
    for sock in node.inputs:
        if sock.bl_idname == evaluator.GEOMETRY:
            continue
        row = box.row(align=True)
        if sock.is_linked:
            src = sock.links[0].from_node
            row.label(text=f"{sock.name}: ← {getattr(src, 'param_name', '') or src.label or src.bl_label}", icon="LINKED")
            continue
        row.prop(sock, "default_value", text=sock.name)
        if sock.bl_idname != evaluator.BOOL:
            op = row.operator("param.promote_input", text="", icon="DRIVER")
            op.tree_name = tree.name
            op.node_name = node.name
            op.socket_name = sock.name


def draw_sync(context, layout):
    tree = _active_tree(context)
    if tree is None:
        layout.label(text="Kein parametrisches Objekt aktiv", icon="INFO")
        return
    obj = context.active_object
    outs = evaluator.output_nodes(tree)
    col = layout.column(align=True)
    if tree.param_status.startswith("Fehler"):
        col.alert = True
        col.label(text=tree.param_status, icon="ERROR")
    elif tree.param_dirty:
        col.label(text="Veraltet – wird neu berechnet", icon="TIME")
    else:
        col.label(text=tree.param_status or "Aktuell", icon="CHECKMARK")
    for out in outs:
        row = layout.row(align=True)
        row.label(text=out.target.name if out.target else "(kein Objekt)", icon="OUTPUT")
        row.prop(out, "sync_mode", expand=True)
    if graph.is_parametric(obj):
        tool_grid(layout, context, [
            ("param.set_sync", {"mode": "LIVE"}, "Sync", "sync"),
            ("param.set_sync", {"mode": "FROZEN"}, "Aufheben", "unsync"),
            ("param.relink", {}, "Re-link", "relink"),
            ("param.bake", {}, "Bake", "bake"),
        ])
    row = layout.row()
    row.scale_y = 1.4
    row.operator("param.recalculate", text="Neu berechnen", icon_value=icons.get("recalc"))
    dirty = [n for n in tree.nodes if getattr(n, "param_error", "")]
    if dirty:
        box = layout.box()
        box.alert = True
        for n in dirty:
            box.label(text=f"{n.label or n.bl_label}: {n.param_error}", icon="ERROR")


# ---------------------------------------------------------------------------
# 3D viewport

class _ViewPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


class PARAM_PT_main(_ViewPanel, bpy.types.Panel):
    bl_label = "Parametric Design"
    bl_idname = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.scale_y = 1.6
        row.operator("param.setup_workspace", text="Arbeitsbereich", icon_value=icons.get("workspace"))
        row.operator("param.setup_units", text="mm", icon_value=icons.get("units"))
        obj = context.active_object
        if graph.is_parametric(obj):
            layout.label(text=f"{obj.name} · {obj.param_tree.name}", icon="MOD_BUILD")
            if not obj.select_get():
                layout.label(text="Objekt auswählen, um Teile anzufügen", icon="INFO")
        else:
            layout.label(text="Werkzeug wählen → neues Objekt", icon="INFO")
        layout.prop(context.scene.param_settings, "show_overlay")


class PARAM_PT_primitives(_ViewPanel, bpy.types.Panel):
    bl_label = "Grundkörper"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        tool_grid(self.layout, context, [
            ("param.add_part", {"kind": "BOX"}, "Box", "box"),
            ("param.add_part", {"kind": "CYLINDER"}, "Zylinder", "cylinder"),
            ("param.add_part", {"kind": "SPHERE"}, "Kugel", "sphere"),
            ("param.add_part", {"kind": "CONE"}, "Kegel", "cone"),
        ])


class PARAM_PT_sketch(_ViewPanel, bpy.types.Panel):
    bl_label = "Kurven & Skizze"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.param_settings
        wm = context.window_manager
        running = wm.param_sketch_running
        current = wm.param_sketch_tool if running else ""
        tool_grid(layout, context, [
            ("param.sketch_tool", {"tool": "LINE"}, "Linie", "sketch_line", current == "LINE"),
            ("param.sketch_tool", {"tool": "ARC"}, "Bogen", "sketch_arc", current == "ARC"),
            ("param.sketch_tool", {"tool": "CIRCLE"}, "Kreis", "sketch_circle", current == "CIRCLE"),
            ("param.sketch_tool", {"tool": "RECT"}, "Rechteck", "sketch_rect", current == "RECT"),
            ("param.sketch_tool", {"tool": "SELECT"}, "Auswahl", "sketch_select", current == "SELECT"),
            ("param.sketch_delete", {}, "Löschen", "delete"),
            ("param.sketch_construction", {}, "Hilfslinie", "construction"),
        ])
        if running:
            row = layout.row()
            row.scale_y = 1.6
            row.alert = True
            row.operator("param.sketch_stop", text="Skizze beenden (Esc)", icon="CHECKMARK")
        node = sketch_ops.active_sketch(context)
        if node is not None:
            conflict = "Konflikt" in node.sketch_status
            row = layout.row()
            row.alert = conflict
            row.label(text=node.sketch_status, icon="ERROR" if conflict else ("CHECKMARK" if node.sketch_dof == 0 and node.points else "INFO"))
        row = layout.row(align=True)
        row.prop(settings, "sketch_grid")
        row.prop(settings, "show_sketch", text="", icon="HIDE_OFF" if settings.show_sketch else "HIDE_ON")

        layout.label(text="Fertige Profile")
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.prop_enum(settings, "profile_mode", "EXTRUDE")
        row.prop_enum(settings, "profile_mode", "REVOLVE")
        mode = settings.profile_mode
        tool_grid(layout, context, [
            ("param.add_part", {"kind": "RECTANGLE", "profile_mode": mode}, "Rechteck", "rectangle"),
            ("param.add_part", {"kind": "CIRCLE", "profile_mode": mode}, "Kreis", "circle"),
            ("param.add_part", {"kind": "POLYGON", "profile_mode": mode}, "Polygon", "polygon"),
            ("param.add_part", {"kind": "POLYLINE", "profile_mode": mode}, "Polylinie", "polyline"),
        ])


CONSTRAINT_ICONS = {
    "COINCIDENT": "con_coincident", "HORIZONTAL": "con_horizontal", "VERTICAL": "con_vertical",
    "DISTANCE": "con_distance", "PARALLEL": "con_parallel", "PERPENDICULAR": "con_perpendicular",
    "EQUAL": "con_equal", "ANGLE": "con_angle", "POINT_ON_LINE": "con_on_line", "MIDPOINT": "con_midpoint",
    "RADIUS": "con_radius", "TANGENT": "con_tangent", "POINT_ON_CURVE": "con_on_curve",
}


class PARAM_PT_constraints(_ViewPanel, bpy.types.Panel):
    bl_label = "Constraints"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        node = sketch_ops.active_sketch(context)
        if node is None:
            layout.label(text="Zuerst eine Skizze zeichnen", icon="INFO")
            return

        def con(kind, label):
            return ("param.sketch_constrain", {"kind": kind}, label, CONSTRAINT_ICONS[kind])

        tool_grid(layout, context, [
            con("DISTANCE", "Distanz"), con("ANGLE", "Winkel"), con("TANGENT", "Tangent"), con("PARALLEL", "Parallel"),
            con("PERPENDICULAR", "Senkr."), con("EQUAL", "Gleich"), ("param.sketch_fix", {}, "Fix", "con_fix"), con("POINT_ON_LINE", "Kolinear"),
            con("HORIZONTAL", "Horiz."), con("VERTICAL", "Vertikal"), con("COINCIDENT", "Deckung"), con("MIDPOINT", "Mitte"),
            con("RADIUS", "Radius"),
        ])
        if not node.constraints:
            return
        layout.label(text="Aktive Constraints")
        col = layout.column(align=True)
        for index, c in enumerate(node.constraints):
            row = col.row(align=True)
            row.label(text=sketch_nodes.CONSTRAINT_LABELS[c.kind], icon_value=icons.get(CONSTRAINT_ICONS[c.kind]))
            if c.has_value:
                sub = row.row(align=True)
                sub.enabled = not c.expression.strip()
                if c.kind == "ANGLE":
                    sub.prop(c, "value_angle", text="")
                else:
                    sub.prop(c, "value_length", text="")
                row.prop(c, "expression", text="", icon="DRIVER")
            row.operator("param.sketch_constraint_remove", text="", icon="X").index = index


class PARAM_PT_operations(_ViewPanel, bpy.types.Panel):
    bl_label = "Operationen"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        tool_grid(self.layout, context, [
            ("param.boolean", {"operation": "UNION"}, "Union", "bool_union"),
            ("param.boolean", {"operation": "DIFFERENCE"}, "Subtract", "bool_difference"),
            ("param.boolean", {"operation": "INTERSECT"}, "Schnitt", "bool_intersect"),
            ("param.add_operation", {"kind": "SHELL"}, "Shell", "shell"),
            ("param.add_operation", {"kind": "MIRROR"}, "Mirror", "mirror"),
        ])


class PARAM_PT_modifiers(_ViewPanel, bpy.types.Panel):
    bl_label = "Modifier"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        tool_grid(self.layout, context, [
            ("param.add_operation", {"kind": "TRANSFORM"}, "Bewegen", "transform"),
            ("param.add_operation", {"kind": "BEVEL"}, "Bevel", "bevel"),
            ("param.add_operation", {"kind": "SMOOTH"}, "Soften", "smooth"),
        ])


class PARAM_PT_structure(_ViewPanel, bpy.types.Panel):
    bl_label = "Duplicate, Array & Gruppen"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        tool_grid(self.layout, context, [
            ("param.duplicate", {"mode": "COPY"}, "Kopie", "duplicate"),
            ("param.duplicate", {"mode": "INSTANCE"}, "Instance", "instance"),
            ("param.add_operation", {"kind": "LINEAR_ARRAY"}, "Linear", "array_linear"),
            ("param.add_operation", {"kind": "RADIAL_ARRAY"}, "Radial", "array_radial"),
            ("param.group_objects", {}, "Gruppe", "group"),
        ])


class PARAM_PT_parameters(_ViewPanel, bpy.types.Panel):
    bl_label = "Parameter"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        draw_parameters(context, self.layout)


class PARAM_PT_sync(_ViewPanel, bpy.types.Panel):
    bl_label = "Sync & Status"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        draw_sync(context, self.layout)


class PARAM_PT_snap(_ViewPanel, bpy.types.Panel):
    bl_label = "Snap"
    bl_parent_id = "PARAM_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        ts = context.scene.tool_settings
        row = layout.row()
        row.scale_y = 1.6
        row.prop(ts, "use_snap", text="Snap an" if ts.use_snap else "Snap aus", toggle=True, icon="SNAP_ON" if ts.use_snap else "SNAP_OFF")
        props = ts.bl_rna.properties
        col = layout.column(align=True)
        col.label(text="Ziele")
        col.prop(ts, "snap_elements_base" if "snap_elements_base" in props else "snap_elements", expand=True)
        if "snap_elements_individual" in props:
            col.prop(ts, "snap_elements_individual", expand=True)
        layout.label(text="Modus")
        layout.prop(ts, "snap_target", expand=True)


LEVEL_ICONS = {"OK": "STRIP_COLOR_04", "WARN": "STRIP_COLOR_03", "FAIL": "STRIP_COLOR_01"}


class PARAM_PT_print(_ViewPanel, bpy.types.Panel):
    bl_label = "3D-Druck"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene.param_print, "preset", expand=True)
        tool_grid(layout, context, [
            ("param.print_check", {}, "Prüfen", "print_check"),
            ("param.export_stl", {}, "STL", "export"),
        ])
        report = printing.report_of(scene)
        if report is None:
            return
        obj = context.active_object
        box = layout.box()
        row = box.row()
        row.label(text=report["verdict"], icon=LEVEL_ICONS[report["level"]])
        if obj is None or obj.name != report["object"]:
            box.label(text=f"gilt für {report['object']}", icon="INFO")
        box.label(text=f"{report['size']} · {report['volume']} · {report['parts']} Teil(e)")
        active = printing.runtime["active"] if printing.runtime["object"] == report["object"] else ""
        for item in report["checks"]:
            col = box.column(align=True)
            row = col.row(align=True)
            row.label(text=item["label"], icon=LEVEL_ICONS[item["level"]])
            if item["count"]:
                row.operator("param.print_highlight", text="", icon="HIDE_OFF" if active == item["id"] else "HIDE_ON",
                             depress=active == item["id"]).check_id = item["id"]
            sub = col.row()
            sub.enabled = item["level"] != "OK"
            sub.label(text=item["text"], icon="BLANK1")


class PARAM_PT_print_profile(_ViewPanel, bpy.types.Panel):
    bl_label = "Druckprofil"
    bl_parent_id = "PARAM_PT_print"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        profile = context.scene.param_print
        col = self.layout.column(align=True)
        for name in ("nozzle", "layer_height", "min_wall", "min_detail", "max_overhang", "clearance"):
            col.prop(profile, name)
        col = self.layout.column(align=True)
        col.prop(profile, "bed")


def draw_quick_access(self, context):
    """Quick access bar in the tool header of the 3D viewport."""
    if context.mode != "OBJECT":
        return
    layout = self.layout
    wm = context.window_manager
    ts = context.scene.tool_settings
    current = wm.param_sketch_tool if wm.param_sketch_running else ""
    layout.separator()
    row = layout.row(align=True)
    row.scale_x = 1.25
    row.operator("param.add_part", text="", icon_value=icons.get("box")).kind = "BOX"
    row.operator("param.add_part", text="", icon_value=icons.get("sphere")).kind = "SPHERE"
    row.operator("param.sketch_tool", text="", icon_value=icons.get("sketch_line"), depress=current == "LINE").tool = "LINE"
    row = layout.row(align=True)
    row.scale_x = 1.25
    row.operator("param.toggle_snap", text="", icon_value=icons.get("snap"), depress=ts.use_snap)
    row = layout.row(align=True)
    row.scale_x = 1.25
    row.operator("param.group_objects", text="", icon_value=icons.get("group"))
    row.operator("param.duplicate", text="", icon_value=icons.get("duplicate")).mode = "COPY"
    row.operator("param.add_operation", text="", icon_value=icons.get("array_linear")).kind = "LINEAR_ARRAY"
    row = layout.row(align=True)
    row.scale_x = 1.25
    row.operator("param.set_sync", text="", icon_value=icons.get("sync")).mode = "LIVE"
    row.operator("param.set_sync", text="", icon_value=icons.get("unsync")).mode = "FROZEN"


# ---------------------------------------------------------------------------
# Node editor

class _NodePanel:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = CATEGORY

    @classmethod
    def poll(cls, context):
        return getattr(context.space_data, "tree_type", "") == TREE_ID


class PARAM_PT_node_sync(_NodePanel, bpy.types.Panel):
    bl_label = "Sync & Status"

    def draw(self, context):
        space = context.space_data
        if len(space.path) > 1:
            self.layout.operator("param.group_exit", icon="FULLSCREEN_EXIT")
        draw_sync(context, self.layout)


class PARAM_PT_node_parameters(_NodePanel, bpy.types.Panel):
    bl_label = "Parameter"

    def draw(self, context):
        draw_parameters(context, self.layout)


classes = (
    PARAM_PT_main,
    PARAM_PT_primitives,
    PARAM_PT_sketch,
    PARAM_PT_constraints,
    PARAM_PT_operations,
    PARAM_PT_modifiers,
    PARAM_PT_structure,
    PARAM_PT_parameters,
    PARAM_PT_sync,
    PARAM_PT_snap,
    PARAM_PT_print,
    PARAM_PT_print_profile,
    PARAM_PT_node_sync,
    PARAM_PT_node_parameters,
)
