# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from ..core import evaluator
from ..core.evaluator import TREE_ID
from ..ops import graph

BIG = 2.2  # ~44 px buttons at the default UI scale, for stylus and touch
CATEGORY = "Parametric"


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


def _big_grid(layout, columns=2):
    grid = layout.grid_flow(row_major=True, columns=columns, even_columns=True, even_rows=True, align=True)
    grid.scale_y = BIG
    return grid


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
    for node in params:
        row = col.row(align=True)
        row.prop(node, "value", text=node.param_name)
        row.prop(node, "expose", text="", icon="EXPORT" if node.expose else "BLANK1", emboss=node.expose)
    row = layout.row(align=True)
    row.scale_y = 1.4
    row.operator("param.add_parameter", text="Länge", icon="ADD").unit = "LENGTH"
    row.operator("param.add_parameter", text="Winkel", icon="ADD").unit = "ANGLE"
    row.operator("param.add_parameter", text="Zahl", icon="ADD").unit = "NUMBER"

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
        grid = _big_grid(layout)
        grid.operator("param.set_sync", text="Sync (live)", icon="LINKED").mode = "LIVE"
        grid.operator("param.set_sync", text="Sync aufheben", icon="UNLINKED").mode = "FROZEN"
        grid.operator("param.relink", text="Re-link", icon="FILE_REFRESH")
        grid.operator("param.bake", text="Bake", icon="MESH_DATA")
    layout.operator("param.recalculate", text="Neu berechnen", icon="FILE_REFRESH")
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
        row.scale_y = 1.4
        row.operator("param.setup_workspace", text="Arbeitsbereich", icon="WORKSPACE")
        row.operator("param.setup_units", text="mm", icon="DRIVER_DISTANCE")
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
        grid = _big_grid(self.layout)
        for kind, text, icon in (("BOX", "Box", "MESH_CUBE"), ("CYLINDER", "Zylinder", "MESH_CYLINDER"),
                                 ("SPHERE", "Kugel", "MESH_UVSPHERE"), ("CONE", "Kegel", "MESH_CONE")):
            grid.operator("param.add_part", text=text, icon=icon).kind = kind


class PARAM_PT_sketch(_ViewPanel, bpy.types.Panel):
    bl_label = "Kurven & Skizze"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        for mode, label in (("EXTRUDE", "Extrudieren"), ("REVOLVE", "Rotieren")):
            layout.label(text=label)
            grid = _big_grid(layout)
            for kind, text, icon in (("RECTANGLE", "Rechteck", "MESH_PLANE"), ("CIRCLE", "Kreis", "MESH_CIRCLE"),
                                     ("POLYGON", "Polygon", "SEQ_CHROMA_SCOPE"), ("POLYLINE", "Polylinie", "IPO_LINEAR")):
                op = grid.operator("param.add_part", text=text, icon=icon)
                op.kind = kind
                op.profile_mode = mode


class PARAM_PT_operations(_ViewPanel, bpy.types.Panel):
    bl_label = "Operationen & Modifier"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        grid = _big_grid(layout)
        for kind, text, icon in (("TRANSFORM", "Transform", "ORIENTATION_GLOBAL"), ("BEVEL", "Bevel", "MOD_BEVEL"),
                                 ("SMOOTH", "Soften", "MOD_SUBSURF"), ("SHELL", "Shell", "MOD_SOLIDIFY"),
                                 ("MIRROR", "Spiegeln", "MOD_MIRROR"), ("LINEAR_ARRAY", "Array", "MOD_ARRAY"),
                                 ("RADIAL_ARRAY", "Radial", "FORCE_VORTEX")):
            grid.operator("param.add_operation", text=text, icon=icon).kind = kind
        layout.label(text="Boolean (mit 2. gewähltem Objekt)")
        grid = _big_grid(layout, 3)
        grid.operator("param.boolean", text="", icon="SELECT_SUBTRACT").operation = "DIFFERENCE"
        grid.operator("param.boolean", text="", icon="SELECT_EXTEND").operation = "UNION"
        grid.operator("param.boolean", text="", icon="SELECT_INTERSECT").operation = "INTERSECT"


class PARAM_PT_structure(_ViewPanel, bpy.types.Panel):
    bl_label = "Duplizieren & Gruppen"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        grid = _big_grid(self.layout)
        grid.operator("param.duplicate", text="Duplizieren", icon="DUPLICATE").mode = "COPY"
        grid.operator("param.duplicate", text="Instanz", icon="LINKED").mode = "INSTANCE"
        grid.operator("param.group_objects", text="Gruppieren", icon="GROUP")


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


class PARAM_PT_print(_ViewPanel, bpy.types.Panel):
    bl_label = "3D-Druck"
    bl_parent_id = "PARAM_PT_main"

    def draw(self, context):
        layout = self.layout
        grid = _big_grid(layout)
        grid.operator("param.print_check", text="Druck-Check", icon="CHECKMARK")
        grid.operator("param.export_stl", text="STL", icon="EXPORT")
        report = context.scene.get("param_print_report")
        if report:
            box = layout.box()
            for i, line in enumerate(report.split("\n")):
                box.label(text=line, icon=("CHECKMARK" if line == "Druckbereit" else "ERROR") if i == 0 else "BLANK1")


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
    PARAM_PT_operations,
    PARAM_PT_structure,
    PARAM_PT_parameters,
    PARAM_PT_sync,
    PARAM_PT_snap,
    PARAM_PT_print,
    PARAM_PT_node_sync,
    PARAM_PT_node_parameters,
)
