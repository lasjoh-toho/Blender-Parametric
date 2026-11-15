# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport tools: every tool adds nodes to the graph of the active object."""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..core import evaluator, scheduler
from . import graph

PART_ITEMS = [
    ("BOX", "Box", "", "MESH_CUBE", 0),
    ("CYLINDER", "Zylinder", "", "MESH_CYLINDER", 1),
    ("SPHERE", "Kugel", "", "MESH_UVSPHERE", 2),
    ("CONE", "Kegel", "", "MESH_CONE", 3),
    ("RECTANGLE", "Rechteck", "", "MESH_PLANE", 4),
    ("CIRCLE", "Kreis", "", "MESH_CIRCLE", 5),
    ("POLYGON", "Polygon", "", "SEQ_CHROMA_SCOPE", 6),
    ("POLYLINE", "Polylinie", "", "IPO_LINEAR", 7),
    ("SKETCH", "Skizze", "", "GREASEPENCIL", 8),
]

OPERATION_ITEMS = [
    ("TRANSFORM", "Verschieben/Rotieren/Skalieren", "", "ORIENTATION_GLOBAL", 0),
    ("BEVEL", "Bevel / Fase", "", "MOD_BEVEL", 1),
    ("SMOOTH", "Soften", "", "MOD_SUBSURF", 2),
    ("SHELL", "Shell", "", "MOD_SOLIDIFY", 3),
    ("MIRROR", "Spiegeln", "", "MOD_MIRROR", 4),
    ("LINEAR_ARRAY", "Lineares Array", "", "MOD_ARRAY", 5),
    ("RADIAL_ARRAY", "Radiales Array", "", "FORCE_VORTEX", 6),
]


def _active_parametric(context):
    obj = context.active_object
    return obj if graph.is_parametric(obj) else None


class PARAM_OT_add_part(bpy.types.Operator):
    """Add a parametric part. With a parametric object active, the part is joined into its graph"""

    bl_idname = "param.add_part"
    bl_label = "Parametrisches Teil hinzufügen"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(name="Art", items=PART_ITEMS, default="BOX")
    profile_mode: EnumProperty(
        name="Profil",
        items=[("EXTRUDE", "Extrudieren", ""), ("REVOLVE", "Rotieren", "")],
        default="EXTRUDE",
    )
    new_object: BoolProperty(
        name="Neues Objekt",
        description="Immer ein neues Objekt anlegen, statt das Teil dem aktiven Objekt hinzuzufügen",
        default=False,
    )

    @classmethod
    def description(cls, context, props):
        return f"{dict((i[0], i[1]) for i in PART_ITEMS)[props.kind]} als Node anlegen"

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        obj = _active_parametric(context)
        if obj is not None and obj.select_get() and not self.new_object:
            graph.add_part_to(context, obj, self.kind, self.profile_mode)
            scheduler.flush()
            return {"FINISHED"}
        label = graph.part_label(self.kind)
        name = f"Param {label}"
        graph.create_object(context, name, lambda tree: graph.build_part(tree, self.kind, (0, 0), self.profile_mode))
        return {"FINISHED"}


class PARAM_OT_add_operation(bpy.types.Operator):
    """Add an operation to the active parametric object (inserted before its output)"""

    bl_idname = "param.add_operation"
    bl_label = "Operation hinzufügen"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(name="Operation", items=OPERATION_ITEMS, default="BEVEL")

    @classmethod
    def poll(cls, context):
        if _active_parametric(context) is None:
            cls.poll_message_set("Wähle zuerst ein parametrisches Objekt")
            return False
        return True

    @classmethod
    def description(cls, context, props):
        return f"{dict((i[0], i[1]) for i in OPERATION_ITEMS)[props.kind]} als Node einfügen"

    def execute(self, context):
        obj = _active_parametric(context)
        tree = obj.param_tree
        out = graph.output_for(tree, obj)
        if out is None:
            self.report({"ERROR"}, "Der Graph hat keinen Output-Node")
            return {"CANCELLED"}
        with scheduler.suspended():
            node = tree.nodes.new(graph.OPERATIONS[self.kind])
            graph.insert_before_output(tree, out, node)
            if self.kind == "LINEAR_ARRAY":
                width = max(obj.dimensions.x / max(obj.scale.x, 1e-9), 1.0)
                node.inputs["Versatz"].default_value = (width * 1.25, 0.0, 0.0)
        scheduler.request(tree)
        scheduler.flush()
        return {"FINISHED"}


class PARAM_OT_boolean(bpy.types.Operator):
    """Boolean with another selected object (it stays linked and becomes a wireframe cutter) or with a new cylinder"""

    bl_idname = "param.boolean"
    bl_label = "Boolean"
    bl_options = {"REGISTER", "UNDO"}

    operation: EnumProperty(
        name="Operation",
        items=[
            ("DIFFERENCE", "Differenz", "", "SELECT_SUBTRACT", 0),
            ("UNION", "Vereinigung", "", "SELECT_EXTEND", 1),
            ("INTERSECT", "Schnitt", "", "SELECT_INTERSECT", 2),
        ],
        default="DIFFERENCE",
    )

    @classmethod
    def poll(cls, context):
        if _active_parametric(context) is None:
            cls.poll_message_set("Wähle zuerst ein parametrisches Objekt")
            return False
        return True

    def execute(self, context):
        obj = _active_parametric(context)
        tree = obj.param_tree
        out = graph.output_for(tree, obj)
        others = [o for o in context.selected_objects if o != obj and o.type == "MESH"]
        with scheduler.suspended():
            node = tree.nodes.new("PARAM_N_Boolean")
            node.operation = self.operation
            graph.insert_before_output(tree, out, node)
            if others:
                cutter = others[0]
                src = graph.add_node(tree, "PARAM_N_ObjectInput", (node.location.x - graph.NODE_GAP, node.location.y - 260))
                src.source = cutter
                src.relative = True
                cutter.display_type = "WIRE"
                cutter.hide_render = True
                tree.links.new(src.outputs["Geometrie"], node.inputs["B"])
            else:
                cyl = graph.add_node(tree, "PARAM_N_Cylinder", (node.location.x - 2 * graph.NODE_GAP, node.location.y - 260))
                cyl.inputs["Radius"].default_value = 5.0
                height = max(obj.dimensions.z / max(obj.scale.z, 1e-9), 1.0) + 2.0
                cyl.inputs["Höhe"].default_value = height
                move = graph.add_node(tree, "PARAM_N_Transform", (node.location.x - graph.NODE_GAP, node.location.y - 260))
                move.inputs["Verschieben"].default_value = (0.0, 0.0, -1.0)
                tree.links.new(cyl.outputs["Geometrie"], move.inputs["Geometrie"])
                tree.links.new(move.outputs["Geometrie"], node.inputs["B"])
        graph.select_only(context, obj)
        scheduler.request(tree)
        scheduler.flush()
        return {"FINISHED"}


class PARAM_OT_add_parameter(bpy.types.Operator):
    """Add a named parameter to the graph of the active object"""

    bl_idname = "param.add_parameter"
    bl_label = "Parameter hinzufügen"
    bl_options = {"REGISTER", "UNDO"}

    unit: EnumProperty(
        name="Einheit",
        items=[("LENGTH", "Länge", ""), ("ANGLE", "Winkel", ""), ("NUMBER", "Zahl", "")],
        default="LENGTH",
    )

    @classmethod
    def poll(cls, context):
        return _active_parametric(context) is not None

    def execute(self, context):
        tree = context.active_object.param_tree
        idname = {"LENGTH": "PARAM_N_LengthParam", "ANGLE": "PARAM_N_AngleParam", "NUMBER": "PARAM_N_NumberParam"}[self.unit]
        loc = graph.frame_location(tree)
        node = graph.add_node(tree, idname, (loc.x - graph.NODE_GAP, loc.y - 120))
        tree.nodes.active = node
        return {"FINISHED"}


class PARAM_OT_promote_input(bpy.types.Operator):
    """Turn a node input into a named parameter (keeps its current value)"""

    bl_idname = "param.promote_input"
    bl_label = "Als Parameter"
    bl_options = {"REGISTER", "UNDO"}

    tree_name: StringProperty()
    node_name: StringProperty()
    socket_name: StringProperty()
    param_name: StringProperty(name="Name", default="")

    def invoke(self, context, event):
        if not self.param_name:
            self.param_name = _slug(self.socket_name)
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        tree = bpy.data.node_groups.get(self.tree_name)
        node = tree.nodes.get(self.node_name) if tree else None
        sock = node.inputs.get(self.socket_name) if node else None
        if sock is None or sock.is_linked:
            return {"CANCELLED"}
        idname = {
            evaluator.LENGTH: "PARAM_N_LengthParam",
            evaluator.ANGLE: "PARAM_N_AngleParam",
        }.get(sock.bl_idname, "PARAM_N_NumberParam")
        with scheduler.suspended():
            param = graph.add_node(tree, idname, (node.location.x - graph.NODE_GAP, node.location.y - 40 * len(node.inputs)))
            name = self.param_name or _slug(self.socket_name)
            used = {getattr(n, "param_name", "") for n in tree.nodes if n != param}
            base, i = name, 2
            while name in used:
                name = f"{base}{i}"
                i += 1
            param.param_name = name
            value = sock.default_value
            if sock.bl_idname == evaluator.VECTOR:
                value = value[0]
            param.value = value
            tree.links.new(param.outputs["Wert"], sock)
        scheduler.request(tree)
        return {"FINISHED"}


def _slug(text):
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
    out = "".join(c if c.isalnum() else "_" for c in text.translate(table).lower()).strip("_")
    if not out or out[0].isdigit():
        out = "p_" + out
    return out


class PARAM_OT_duplicate(bpy.types.Operator):
    """Duplicate: copy object and graph (independent). Instance: shared graph and mesh, own transform"""

    bl_idname = "param.duplicate"
    bl_label = "Duplizieren"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Art",
        items=[
            ("COPY", "Duplizieren", "Objekt und Graph kopieren, danach unabhängig"),
            ("INSTANCE", "Instanz", "Geteilter Graph und geteiltes Mesh, nur der Transform ist eigen"),
        ],
        default="COPY",
    )
    move: BoolProperty(name="Danach verschieben", default=True, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return _active_parametric(context) is not None

    def execute(self, context):
        obj = context.active_object
        new = obj.copy()
        for coll in obj.users_collection:
            coll.objects.link(new)
        if self.mode == "COPY":
            new.data = obj.data.copy()
            tree = obj.param_tree.copy()
            new.param_tree = tree
            for out in evaluator.output_nodes(tree):
                if out.target == obj:
                    out.target = new
            scheduler.request(tree)
        graph.select_only(context, new)
        if self.move and not bpy.app.background:
            bpy.ops.transform.translate("INVOKE_DEFAULT")
        return {"FINISHED"}


class PARAM_OT_group_objects(bpy.types.Operator):
    """Group the selected parametric objects: a new object whose graph uses their graphs as groups"""

    bl_idname = "param.group_objects"
    bl_label = "Gruppieren"
    bl_options = {"REGISTER", "UNDO"}

    hide_sources: BoolProperty(name="Einzelteile ausblenden", default=True)

    @classmethod
    def poll(cls, context):
        return any(graph.is_parametric(o) for o in context.selected_objects)

    def execute(self, context):
        members = [o for o in context.selected_objects if graph.is_parametric(o)]
        active = context.active_object if context.active_object in members else members[0]
        origin = active.matrix_world.to_translation()
        from mathutils import Matrix

        def build(tree):
            join = graph.add_node(tree, "PARAM_N_Join", (0, 0))
            for i, member in enumerate(members):
                grp = graph.add_node(tree, "PARAM_N_Group", (-2 * graph.NODE_GAP, -i * 220))
                grp.subtree = member.param_tree
                grp.sync_sockets()
                grp.label = member.name
                rel = Matrix.Translation(-origin) @ member.matrix_world
                loc, rot, scale = rel.decompose()
                move = graph.add_node(tree, "PARAM_N_Transform", (-graph.NODE_GAP, -i * 220))
                move.inputs["Verschieben"].default_value = tuple(loc)
                move.inputs["Rotieren (Grad)"].default_value = tuple(math.degrees(a) for a in rot.to_euler("XYZ"))
                move.inputs["Skalieren"].default_value = tuple(scale)
                tree.links.new(grp.outputs["Geometrie"], move.inputs["Geometrie"])
                tree.links.new(move.outputs["Geometrie"], join.inputs["Geometrie"])
            return join.outputs["Geometrie"]

        cursor = context.scene.cursor.location.copy()
        context.scene.cursor.location = origin
        try:
            obj, _tree = graph.create_object(context, "Param Gruppe", build)
        finally:
            context.scene.cursor.location = cursor
        if self.hide_sources:
            for member in members:
                member.hide_set(True)
                member.hide_render = True
        graph.select_only(context, obj)
        return {"FINISHED"}


class PARAM_OT_group_sync_sockets(bpy.types.Operator):
    """Update the inputs of the group node from the exposed parameters of its graph"""

    bl_idname = "param.group_sync_sockets"
    bl_label = "Eingänge aktualisieren"
    bl_options = {"REGISTER", "UNDO"}

    node_name: StringProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None)
        node = tree.nodes.get(self.node_name) if tree else None
        if node is None:
            return {"CANCELLED"}
        node.sync_sockets()
        scheduler.request(tree)
        return {"FINISHED"}


class PARAM_OT_group_enter(bpy.types.Operator):
    """Open the graph of the group node in place"""

    bl_idname = "param.group_enter"
    bl_label = "Gruppe öffnen"

    node_name: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == "NODE_EDITOR"

    def execute(self, context):
        space = context.space_data
        tree = space.edit_tree
        node = tree.nodes.get(self.node_name) if tree else (tree.nodes.active if tree else None)
        if node is None or node.bl_idname != "PARAM_N_Group" or node.subtree is None:
            return {"CANCELLED"}
        space.path.append(node.subtree, node=node)
        return {"FINISHED"}


class PARAM_OT_group_exit(bpy.types.Operator):
    """Leave the opened group"""

    bl_idname = "param.group_exit"
    bl_label = "Gruppe verlassen"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == "NODE_EDITOR" and len(space.path) > 1

    def execute(self, context):
        context.space_data.path.pop()
        return {"FINISHED"}


class PARAM_OT_toggle_snap(bpy.types.Operator):
    """Snap on/off"""

    bl_idname = "param.toggle_snap"
    bl_label = "Snap umschalten"

    def execute(self, context):
        ts = context.scene.tool_settings
        ts.use_snap = not ts.use_snap
        return {"FINISHED"}


classes = (
    PARAM_OT_add_part,
    PARAM_OT_add_operation,
    PARAM_OT_boolean,
    PARAM_OT_add_parameter,
    PARAM_OT_promote_input,
    PARAM_OT_duplicate,
    PARAM_OT_group_objects,
    PARAM_OT_group_sync_sockets,
    PARAM_OT_group_enter,
    PARAM_OT_group_exit,
    PARAM_OT_toggle_snap,
)
