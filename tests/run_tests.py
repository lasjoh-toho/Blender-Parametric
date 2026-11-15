# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless tests.

Run with Blender:   blender -b --factory-startup --python tests/run_tests.py
or with the bpy module from PyPI:   python tests/run_tests.py
"""

import math
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402  (must come first when using the bpy module)
import bmesh  # noqa: E402

import parametric_design as pd  # noqa: E402
from parametric_design.core import evaluator, expressions, geometry, scheduler  # noqa: E402
from parametric_design.ops import graph  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def mesh_stats(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    s = geometry.stats(bm)
    bm.free()
    return s


def approx(a, b, tol=1e-3):
    assert abs(a - b) <= tol * max(1.0, abs(b)), f"{a} != {b}"


def new_object(kind, profile_mode="EXTRUDE"):
    ctx = bpy.context
    bpy.ops.param.add_part(kind=kind, profile_mode=profile_mode, new_object=True)
    return ctx.active_object


def node(tree, idname):
    return next(n for n in tree.nodes if n.bl_idname == idname)


# ---------------------------------------------------------------------------

@test
def expressions_are_safe():
    approx(expressions.evaluate("a * 2 + b", {"a": 3, "b": 1}), 7)
    approx(expressions.evaluate("sin(90)"), 1)
    approx(expressions.evaluate("2,5"), 2.5)
    approx(expressions.evaluate("max(1, 4) if a > 0 else 0", {"a": 1}), 4)
    for bad in ("__import__('os')", "a.b", "[1]", "open('x')", "lambda: 1", "2 ** 999999"):
        try:
            expressions.evaluate(bad, {"a": 1})
        except expressions.ExpressionError:
            continue
        raise AssertionError(f"accepted {bad}")


@test
def box_is_watertight_and_sized():
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    box.inputs["Breite"].default_value = 40
    scheduler.flush()
    s = mesh_stats(obj)
    approx(s["dimensions"][0], 40)
    approx(s["dimensions"][2], 20)
    approx(s["volume"], 40 * 20 * 20)
    assert s["non_manifold_edges"] == 0
    assert not tree.param_status.startswith("Fehler"), tree.param_status


@test
def primitives_build():
    for kind in ("CYLINDER", "SPHERE", "CONE"):
        obj = new_object(kind)
        s = mesh_stats(obj)
        assert s["faces"] > 10, kind
        assert s["non_manifold_edges"] == 0, (kind, s)


@test
def profiles_extrude_and_revolve():
    for kind in ("RECTANGLE", "CIRCLE", "POLYGON", "POLYLINE"):
        obj = new_object(kind, "EXTRUDE")
        s = mesh_stats(obj)
        assert s["non_manifold_edges"] == 0, (kind, s, obj.param_tree.param_status)
        assert s["volume"] > 0, kind
    rect = new_object("RECTANGLE", "EXTRUDE")
    approx(mesh_stats(rect)["volume"], 30 * 20 * 10)
    for kind in ("RECTANGLE", "CIRCLE", "POLYLINE"):
        obj = new_object(kind, "REVOLVE")
        s = mesh_stats(obj)
        assert s["non_manifold_edges"] == 0, (kind, s, obj.param_tree.param_status)
        assert s["volume"] > 0, kind
    # Rectangle 10 x 30 revolved at 20 from the axis: ring from r=15..25, height 30
    obj = new_object("RECTANGLE", "REVOLVE")
    expected = math.pi * (25 ** 2 - 15 ** 2) * 30
    s = mesh_stats(obj)
    assert abs(s["volume"] - expected) / expected < 0.01, (s["volume"], expected)
    # partial revolve
    rev = node(obj.param_tree, "PARAM_N_Revolve")
    rev.inputs["Winkel"].default_value = math.radians(180)
    scheduler.flush()
    s = mesh_stats(obj)
    assert s["non_manifold_edges"] == 0, s
    assert abs(s["volume"] - expected / 2) / expected < 0.01, (s["volume"], expected / 2)


@test
def rounded_rectangle():
    obj = new_object("RECTANGLE")
    rect = node(obj.param_tree, "PARAM_N_Rectangle")
    rect.inputs["Eckradius"].default_value = 5
    scheduler.flush()
    s = mesh_stats(obj)
    expected = (30 * 20 - (4 - math.pi) * 25) * 10
    assert abs(s["volume"] - expected) / expected < 0.01


@test
def operations_on_box():
    obj = new_object("BOX")
    for kind in ("BEVEL", "TRANSFORM", "LINEAR_ARRAY", "MIRROR", "SMOOTH", "RADIAL_ARRAY"):
        bpy.ops.param.add_operation(kind=kind)
        status = obj.param_tree.param_status
        assert not status.startswith("Fehler"), (kind, status)
    s = mesh_stats(obj)
    assert s["faces"] > 100


@test
def array_count():
    obj = new_object("BOX")
    bpy.ops.param.add_operation(kind="LINEAR_ARRAY")
    arr = node(obj.param_tree, "PARAM_N_LinearArray")
    arr.inputs["Anzahl"].default_value = 4
    scheduler.flush()
    s = mesh_stats(obj)
    assert s["islands"] == 4, s
    approx(s["volume"], 4 * 20 ** 3)


@test
def shell_makes_wall():
    obj = new_object("BOX")
    bpy.ops.param.add_operation(kind="SHELL")
    s = mesh_stats(obj)
    approx(s["volume"], 20 ** 3 - 16 ** 3, tol=0.02)


@test
def boolean_with_cylinder_cutter():
    obj = new_object("BOX")
    bpy.ops.param.boolean(operation="DIFFERENCE")
    s = mesh_stats(obj)
    expected = 20 ** 3 - math.pi * 25 * 20
    assert abs(s["volume"] - expected) / expected < 0.02, (s["volume"], expected, obj.param_tree.param_status)
    assert s["non_manifold_edges"] == 0


@test
def boolean_with_object_follows_cutter():
    ctx = bpy.context
    base = new_object("BOX")
    cutter = new_object("CYLINDER")
    cutter.location = base.location.copy()
    cutter.location.z -= 1
    base.select_set(True)
    cutter.select_set(True)
    ctx.view_layer.objects.active = base
    bpy.ops.param.boolean(operation="DIFFERENCE")
    v1 = mesh_stats(base)["volume"]
    assert v1 < 20 ** 3 - 100, v1
    # make the cutter bigger -> dependent base is re-evaluated
    node(cutter.param_tree, "PARAM_N_Cylinder").inputs["Radius"].default_value = 5
    scheduler.flush()
    v2 = mesh_stats(base)["volume"]
    assert v2 > v1, (v1, v2)


@test
def parameters_and_formula():
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    with scheduler.suspended():
        w = graph.add_node(tree, "PARAM_N_LengthParam", (-400, 0))
        w.param_name = "breite"
        w.value = 50
        f = graph.add_node(tree, "PARAM_N_Formula", (-200, -100))
        f.expression = "breite / 2"
        tree.links.new(w.outputs["Wert"], box.inputs["Breite"])
        tree.links.new(f.outputs["Ergebnis"], box.inputs["Höhe"])
    scheduler.request(tree)
    scheduler.flush()
    s = mesh_stats(obj)
    approx(s["dimensions"][0], 50)
    approx(s["dimensions"][2], 25)
    w.value = 80
    scheduler.flush()
    s = mesh_stats(obj)
    approx(s["dimensions"][2], 40)


@test
def errors_are_reported_and_recover():
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    before = mesh_stats(obj)["volume"]
    box.inputs["Breite"].default_value = 0
    scheduler.flush()
    assert tree.param_status.startswith("Fehler"), tree.param_status
    assert box.param_error
    assert mesh_stats(obj)["volume"] == before  # old mesh is kept
    box.inputs["Breite"].default_value = 10
    scheduler.flush()
    assert not box.param_error
    assert not tree.param_status.startswith("Fehler")


@test
def sync_freeze_relink_bake():
    ctx = bpy.context
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    bpy.ops.param.set_sync(mode="FROZEN")
    box.inputs["Höhe"].default_value = 50
    scheduler.flush()
    approx(mesh_stats(obj)["dimensions"][2], 20)
    bpy.ops.param.relink()
    approx(mesh_stats(obj)["dimensions"][2], 50)
    bpy.ops.param.bake("EXEC_DEFAULT")
    assert obj.param_tree is None
    approx(mesh_stats(obj)["dimensions"][2], 50)


@test
def duplicate_and_instance():
    ctx = bpy.context
    obj = new_object("BOX")
    bpy.ops.param.duplicate(mode="COPY", move=False)
    copy = ctx.active_object
    assert copy != obj and copy.param_tree != obj.param_tree and copy.data != obj.data
    node(copy.param_tree, "PARAM_N_Box").inputs["Höhe"].default_value = 33
    scheduler.flush()
    approx(mesh_stats(copy)["dimensions"][2], 33)
    approx(mesh_stats(obj)["dimensions"][2], 20)

    graph.select_only(ctx, obj)
    bpy.ops.param.duplicate(mode="INSTANCE", move=False)
    inst = ctx.active_object
    assert inst.param_tree == obj.param_tree and inst.data == obj.data
    node(obj.param_tree, "PARAM_N_Box").inputs["Höhe"].default_value = 44
    scheduler.flush()
    approx(mesh_stats(inst)["dimensions"][2], 44)


@test
def group_with_exposed_parameter():
    ctx = bpy.context
    part = new_object("CYLINDER")
    ptree = part.param_tree
    cyl = node(ptree, "PARAM_N_Cylinder")
    with scheduler.suspended():
        r = graph.add_node(ptree, "PARAM_N_LengthParam", (-300, 0))
        r.param_name = "radius"
        r.value = 4
        r.expose = True
        ptree.links.new(r.outputs["Wert"], cyl.inputs["Radius"])
    scheduler.request(ptree)
    graph.select_only(ctx, part)
    bpy.ops.param.group_objects()
    grp_obj = ctx.active_object
    gtree = grp_obj.param_tree
    gnode = node(gtree, "PARAM_N_Group")
    assert "radius" in gnode.inputs, [s.name for s in gnode.inputs]
    approx(mesh_stats(grp_obj)["dimensions"][0], 8, tol=0.01)
    gnode.inputs["radius"].default_value = 6
    scheduler.flush()
    approx(mesh_stats(grp_obj)["dimensions"][0], 12, tol=0.01)
    approx(mesh_stats(part)["dimensions"][0], 8, tol=0.01)  # the original keeps its own value
    # editing the sub-graph updates the group object
    node(ptree, "PARAM_N_Cylinder").inputs["Höhe"].default_value = 7
    scheduler.flush()
    approx(mesh_stats(grp_obj)["dimensions"][2], 7)


@test
def add_part_joins_into_active_object():
    ctx = bpy.context
    obj = new_object("BOX")
    ctx.scene.cursor.location = obj.location + __import__("mathutils").Vector((40, 0, 0))
    bpy.ops.param.add_part(kind="SPHERE")
    ctx.scene.cursor.location = (0, 0, 0)
    assert ctx.active_object == obj
    s = mesh_stats(obj)
    assert s["islands"] == 2, s
    assert any(n.bl_idname == "PARAM_N_Join" for n in obj.param_tree.nodes)


@test
def promote_input_creates_parameter():
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    bpy.ops.param.promote_input("EXEC_DEFAULT", tree_name=tree.name, node_name=box.name, socket_name="Höhe", param_name="hoehe")
    p = next(n for n in tree.nodes if getattr(n, "param_name", "") == "hoehe")
    approx(p.value, 20)
    p.value = 12
    scheduler.flush()
    approx(mesh_stats(obj)["dimensions"][2], 12)


@test
def print_check_and_stl_export():
    import json
    ctx = bpy.context
    bpy.ops.param.setup_units()
    obj = new_object("BOX")
    bpy.ops.param.print_check()
    report = json.loads(ctx.scene["param_print_report"])
    assert report["verdict"] == "Druckbereit", report
    assert report["size"] == "20.00 × 20.00 × 20.00 mm", report
    assert {c["id"]: c["level"] for c in report["checks"]} == {
        "watertight": "OK", "normals": "OK", "build_volume": "OK", "wall": "OK",
        "overhang": "OK", "stability": "OK", "slender": "OK"}, report
    path = os.path.join(tempfile.mkdtemp(), "box.stl")
    bpy.ops.param.export_stl(filepath=path)
    assert os.path.getsize(path) == 84 + 50 * 12, os.path.getsize(path)


def sketch_of(obj):
    return node(obj.param_tree, "PARAM_N_Sketch")


def select(sk, points=(), lines=(), circles=()):
    sk.clear_selection()
    for i in points:
        sk.points[i].select = True
    for i in lines:
        sk.lines[i].select = True
    for i in circles:
        sk.circles[i].select = True


def _block(size, offset=(0.0, 0.0, 0.0), bm=None):
    """A box of ``size`` mm standing on Z = offset z."""
    from mathutils import Matrix
    bm = bm or bmesh.new()
    matrix = Matrix.Translation((offset[0], offset[1], offset[2] + size[2] / 2)) @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
    return bm


def _levels(bm, profile=None):
    from parametric_design.core import print_check
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    checks = print_check.run(bm, dict(profile or print_check.FDM))
    return {c.id: c for c in checks}


@test
def print_checks_find_problems():
    from parametric_design.core import print_check
    cube = _levels(_block((20, 20, 20)))
    assert all(c.level == "OK" for c in cube.values()), {k: (c.level, c.text) for k, c in cube.items()}
    approx(cube["stability"].value, 45.0)
    approx(cube["wall"].value, 20.0)

    plate = _levels(_block((20, 20, 0.5)))
    assert plate["wall"].level == "FAIL" and plate["wall"].faces, plate["wall"].text
    approx(plate["wall"].value, 0.5)

    tower = _levels(_block((5, 5, 40)))
    assert tower["slender"].level == "FAIL", tower["slender"].text
    approx(tower["slender"].value, 8.0)
    assert tower["stability"].level == "WARN", tower["stability"].text

    mushroom = _block((10, 10, 10))
    _block((30, 30, 5), (0, 0, 10), mushroom)
    mushroom = _levels(mushroom)
    assert mushroom["overhang"].level == "WARN", mushroom["overhang"].text
    approx(mushroom["overhang"].value, 30 * 30)  # the bed carries the lower block
    assert "über 45°" in mushroom["overhang"].text, mushroom["overhang"].text

    leaning = _block((10, 10, 10))
    _block((10, 10, 10), (30, 0, 10), leaning)
    _block((10, 10, 10), (60, 0, 10), leaning)
    assert _levels(leaning)["stability"].level == "FAIL"

    big = _levels(_block((300, 20, 20)))
    assert big["build_volume"].level == "FAIL", big["build_volume"].text
    assert _levels(_block((240, 20, 20), ), print_check.RESIN)["build_volume"].level == "FAIL"

    holed = _block((20, 20, 20))
    bmesh.ops.delete(holed, geom=[holed.faces[:][0]], context="FACES")
    holed = _levels(holed)
    assert holed["watertight"].level == "FAIL" and holed["watertight"].faces
    assert "stability" not in holed

    inside_out = _block((20, 20, 20))
    bmesh.ops.reverse_faces(inside_out, faces=inside_out.faces[:])
    assert _levels(inside_out)["normals"].level == "FAIL"
    assert print_check.worst(plate.values()) == "FAIL" and print_check.worst(cube.values()) == "OK"


@test
def print_check_reports_thin_shell_and_highlight():
    import json
    from parametric_design.ops import printing
    ctx = bpy.context
    bpy.ops.param.setup_units()
    obj = new_object("BOX")
    bpy.ops.param.add_operation(kind="SHELL")
    shell = node(obj.param_tree, "PARAM_N_Shell")
    shell.inputs["Dicke"].default_value = 0.5
    scheduler.flush()
    bpy.ops.param.print_check()
    report = json.loads(ctx.scene["param_print_report"])
    wall = next(c for c in report["checks"] if c["id"] == "wall")
    assert wall["level"] == "FAIL" and wall["count"] > 0, wall
    assert report["verdict"] == "So nicht druckbar", report
    assert printing.runtime["triangles"]["wall"], "no faces to highlight"
    bpy.ops.param.print_highlight(check_id="wall")
    assert printing.runtime["active"] == "wall"
    bpy.ops.param.print_highlight(check_id="wall")
    assert printing.runtime["active"] == ""
    ctx.scene.param_print.preset = "RESIN"
    approx(ctx.scene.param_print.min_wall, 0.5)
    bpy.ops.param.print_check()
    report = json.loads(ctx.scene["param_print_report"])
    assert next(c for c in report["checks"] if c["id"] == "wall")["level"] == "OK", report
    ctx.scene.param_print.preset = "FDM"


@test
def parameter_range_and_lock():
    bpy.ops.param.setup_units()
    obj = new_object("BOX")
    tree = obj.param_tree
    bpy.ops.param.add_parameter(unit="LENGTH")
    p = tree.nodes.active
    p.value = 5
    p.use_min, p.min_value = True, 2
    p.use_max, p.max_value = True, 30
    p.value = 1
    approx(p.value, 2)
    assert "Minimum" in tree.param_notice, tree.param_notice
    p.value = 50
    approx(p.value, 30)
    p.value = 12
    assert tree.param_notice == ""
    p.min_value = 15  # raising the limit pulls the value along
    approx(p.value, 15)
    p.use_min = False
    p.profile_min = "WALL"
    p.value = 0.1
    approx(p.value, 0.8)
    p.profile_min = "NONE"
    p.value = 7
    p.locked = True
    p.value = 9
    approx(p.value, 7)
    assert "gesperrt" in tree.param_notice
    p.locked = False
    p.value = 9
    approx(p.value, 9)


@test
def proportion_lock_keeps_ratio_and_difference():
    from parametric_design.ops import proportion
    obj = new_object("BOX")
    tree = obj.param_tree
    box = node(tree, "PARAM_N_Box")
    for sock, name in (("Breite", "breite"), ("Tiefe", "tiefe"), ("Höhe", "hoehe")):
        bpy.ops.param.promote_input("EXEC_DEFAULT", tree_name=tree.name, node_name=box.name, socket_name=sock, param_name=name)
    params = {n.param_name: n for n in tree.nodes if getattr(n, "param_name", "")}
    b, t, h = params["breite"], params["tiefe"], params["hoehe"]
    b.value, t.value, h.value = 40, 20, 10
    b.pick = t.pick = True
    assert bpy.ops.param.proportion_lock.poll()
    bpy.ops.param.proportion_lock(kind="RATIO")
    assert len(tree.param_proportions) == 1 and not b.pick
    assert proportion.describe(tree, tree.param_proportions[0]) == "breite : tiefe = 2 : 1"
    b.value = 60
    approx(t.value, 30)
    t.value = 10  # any member leads
    approx(b.value, 20)
    scheduler.flush()
    dims = mesh_stats(obj)["dimensions"]
    approx(dims[0], 20)
    approx(dims[1], 10)
    # a member at its limit holds the whole group
    t.use_min, t.min_value = True, 8
    b.value = 10
    approx(b.value, 20)
    approx(t.value, 10)
    assert "tiefe" in tree.param_notice and "Minimum" in tree.param_notice, tree.param_notice
    # one parameter, one group
    assert isinstance(proportion.lock(tree, [t, h], "DIFFERENCE"), str)
    bpy.ops.param.proportion_unlock(index=0)
    assert len(tree.param_proportions) == 0
    t.use_min = False
    group = proportion.lock(tree, [t, h], "DIFFERENCE")
    assert not isinstance(group, str), group
    h.value = 15
    approx(t.value, 15)
    t.value = 3
    approx(h.value, 3)
    h.locked = True
    t.value = 6
    approx(t.value, 3)
    assert "gesperrt" in tree.param_notice
    assert isinstance(proportion.lock(tree, [b], "RATIO"), str)


@test
def sketch_rectangle_with_dimensions():
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.param.sketch_add(kind="RECT", x1=0, y1=0, x2=31, y2=19)
    obj = bpy.context.active_object
    sk = sketch_of(obj)
    assert len(sk.lines) == 4 and len(sk.constraints) == 4
    approx(mesh_stats(obj)["volume"], 31 * 19 * 10)
    sk.points[0].select = True
    bpy.ops.param.sketch_fix()
    select(sk, lines=[0])
    bpy.ops.param.sketch_constrain(kind="DISTANCE")
    select(sk, lines=[1])
    bpy.ops.param.sketch_constrain(kind="DISTANCE")
    assert sk.sketch_status == "Voll bestimmt", sk.sketch_status
    sk.constraints[4].value = 40
    scheduler.flush()
    approx(mesh_stats(obj)["volume"], 40 * 19 * 10)
    # drive the height with a named parameter
    tree = obj.param_tree
    with scheduler.suspended():
        p = graph.add_node(tree, "PARAM_N_LengthParam", (-400, 0))
        p.param_name = "hoehe"
        p.value = 25
    sk.constraints[5].expression = "hoehe / 2 + 2.5"
    scheduler.flush()
    approx(mesh_stats(obj)["volume"], 40 * 15 * 10)
    p.value = 35
    scheduler.flush()
    approx(mesh_stats(obj)["volume"], 40 * 20 * 10)
    assert mesh_stats(obj)["non_manifold_edges"] == 0


@test
def sketch_repeated_constraint_and_dimension_text():
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.param.sketch_add(kind="RECT", x1=0, y1=0, x2=31, y2=19)
    sk = sketch_of(bpy.context.active_object)
    count = len(sk.constraints)
    select(sk, lines=[0])
    bpy.ops.param.sketch_constrain(kind="HORIZONTAL")
    assert len(sk.constraints) == count, "the same constraint was added twice"
    from parametric_design.ui.overlay import length_text
    scene = bpy.context.scene
    old = (scene.unit_settings.scale_length, scene.unit_settings.length_unit)
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"
    try:
        assert length_text(scene, 25.0) == "25 mm", length_text(scene, 25.0)
        assert length_text(scene, 0.06) == "0.06 mm", length_text(scene, 0.06)
    finally:
        scene.unit_settings.scale_length, scene.unit_settings.length_unit = old


@test
def sketch_hole_and_conflict():
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.param.sketch_add(kind="RECT", x1=0, y1=0, x2=40, y2=30)
    obj = bpy.context.active_object
    bpy.ops.param.sketch_add(kind="CIRCLE", x1=20, y1=15, x2=25, y2=15)
    sk = sketch_of(obj)
    assert len(sk.circles) == 1
    s = mesh_stats(obj)
    expected = (40 * 30 - math.pi * 25) * 10
    assert abs(s["volume"] - expected) / expected < 0.01, (s["volume"], expected)
    assert s["non_manifold_edges"] == 0, s
    select(sk, circles=[0])
    bpy.ops.param.sketch_constrain(kind="RADIUS")
    sk.constraints[len(sk.constraints) - 1].value = 8
    scheduler.flush()
    expected = (40 * 30 - math.pi * 64) * 10
    assert abs(mesh_stats(obj)["volume"] - expected) / expected < 0.01
    # contradicting constraint -> reported, mesh kept
    select(sk, circles=[0])
    bpy.ops.param.sketch_constrain(kind="RADIUS")
    sk.constraints[len(sk.constraints) - 1].value = 3
    scheduler.flush()
    assert "Konflikt" in sk.sketch_status, sk.sketch_status
    assert obj.param_tree.param_status.startswith("Fehler")
    bpy.ops.param.sketch_constraint_remove(index=len(sk.constraints) - 1)
    assert not obj.param_tree.param_status.startswith("Fehler"), obj.param_tree.param_status


@test
def sketch_session_draws_and_drags():
    from parametric_design.ops.sketch_session import SketchSession, pressure_snap
    assert pressure_snap(0.9, True, False) and not pressure_snap(0.1, True, True) and pressure_snap(0.5, True, True)
    assert pressure_snap(1.0, False, False) is False
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.param.sketch_add(kind="LINE", x1=0, y1=0, x2=20, y2=0)
    obj = bpy.context.active_object
    sk = sketch_of(obj)
    session = SketchSession(sk, grid=1.0)
    session.tool = "LINE"
    r = 0.6
    session.press(20.2, 0.1, r, True)            # picks the existing end point
    assert len(sk.points) == 2
    session.press(20.3, 14.8, r, True)           # snaps to the grid and to vertical
    assert (sk.points[2].x, sk.points[2].y) == (20.0, 15.0), (sk.points[2].x, sk.points[2].y)
    assert sk.constraints[len(sk.constraints) - 1].kind == "VERTICAL"
    session.press(0.2, -0.3, r, True)            # closes on the first point
    assert not session.busy and len(sk.lines) == 3
    scheduler.flush()
    approx(mesh_stats(obj)["volume"], 0.5 * 20 * 15 * 10)
    # free drawing with light pen pressure: no grid snap
    session.press(50.3, 50.4, r, pressure_snap(0.1, True, True))
    assert abs(sk.points[3].x - 50.3) < 1e-6
    assert session.cancel() and len(sk.points) == 3  # the stray point is removed again
    # drag a corner: the vertical constraint keeps x of point 2 equal to point 1
    session.tool = "SELECT"
    select(sk, lines=[0])
    bpy.ops.param.sketch_fix()
    session.press(20.0, 15.0, r, False)
    assert session.drag_point == 2
    session.move(27.0, 22.0, r, False)
    scheduler.flush()
    assert session.release()
    scheduler.flush()
    assert abs(sk.points[2].x - 20.0) < 1e-4 and abs(sk.points[2].y - 22.0) < 0.5, (sk.points[2].x, sk.points[2].y)
    # delete a line -> no closed outline -> empty mesh, no error
    select(sk, lines=[2])
    bpy.ops.param.sketch_delete()
    assert len(obj.data.vertices) == 0 and not obj.param_tree.param_status.startswith("Fehler")
    select(sk, points=[2])
    bpy.ops.param.sketch_delete()
    assert len(sk.points) == 2 and len(sk.lines) == 1, (len(sk.points), len(sk.lines))


@test
def sketch_arc_and_tangent():
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    # half disc: arc from (10,0) to (-10,0) around the origin, closed with a line
    bpy.ops.param.sketch_add(kind="ARC", x1=0, y1=0, x2=10, y2=0, x3=-10, y3=0.001)
    obj = bpy.context.active_object
    sk = sketch_of(obj)
    arc = sk.arcs[0]
    bpy.ops.param.sketch_add(kind="LINE", x1=sk.points[arc.end].x, y1=sk.points[arc.end].y, x2=10, y2=0)
    assert len(sk.points) == 3 and len(sk.lines) == 1, (len(sk.points), len(sk.lines))
    expected = 0.5 * math.pi * 100 * 10
    s = mesh_stats(obj)
    assert abs(s["volume"] - expected) / expected < 0.01, (s["volume"], expected)
    assert s["non_manifold_edges"] == 0


class FakeLayout:
    """Accepts every UILayout call and checks that operators and properties exist."""

    def __init__(self, log):
        self.log = log

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def operator(self, idname, **kw):
        module, name = idname.split(".")
        op = getattr(getattr(bpy.ops, module), name)
        rna = op.get_rna_type()
        self.log.append(idname)

        class Props:
            def __setattr__(s, key, value):
                assert key in rna.properties, f"{idname} has no property {key}"
                prop = rna.properties[key]
                if prop.type == "ENUM":
                    assert value in {i.identifier for i in prop.enum_items}, f"{idname}.{key} = {value}"
        return Props()

    def prop(self, data, name, **kw):
        assert hasattr(data, name), f"{data} has no property {name}"

    def prop_enum(self, data, name, value, **kw):
        assert set(kw) <= {"text", "text_ctxt", "translate", "icon"}, f"prop_enum does not take {sorted(kw)}"
        assert value in {i.identifier for i in data.bl_rna.properties[name].enum_items}

    def template_icon(self, icon_value=0, scale=1.0):
        assert icon_value != 0 or bpy.app.background, "icon missing"

    def __getattr__(self, name):
        if name in {"row", "column", "box", "grid_flow", "split", "column_flow", "menu_pie"}:
            return lambda *a, **k: FakeLayout(self.log)
        if name in {"label", "separator", "menu", "context_pointer_set", "template_ID", "operator_context"}:
            return lambda *a, **k: None
        raise AttributeError(name)


class FakeRegion:
    width = 300
    height = 800


@test
def panels_draw_without_errors():
    from parametric_design.ui import icons, panels, pie
    import os
    # every icon referenced in the UI code exists as a file
    import re
    names = set()
    for mod in (panels, pie):
        src = open(mod.__file__, encoding="utf-8").read()
        names |= set(re.findall(r'icons\.get\("([a-z_]+)"\)', src))
        names |= set(re.findall(r'^\s*\(".*"([a-z_]+)"(?:, current == "[A-Z]+")?\),?\s*$', src, flags=re.M))
        names |= set(re.findall(r': "(con_[a-z_]+)"', src))
    missing = sorted(n for n in names if not os.path.exists(os.path.join(icons.ICON_DIR, n + ".png")))
    assert not missing, missing

    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.ops.param.sketch_add(kind="RECT", x1=0, y1=0, x2=30, y2=20)
    obj = bpy.context.active_object
    sk = sketch_of(obj)
    select(sk, lines=[0])
    bpy.ops.param.sketch_constrain(kind="DISTANCE")

    class Ctx:
        scene = bpy.context.scene
        window_manager = bpy.context.window_manager
        preferences = bpy.context.preferences
        active_object = obj
        region = FakeRegion()
        space_data = None
        mode = "OBJECT"

    log = []
    for cls in panels.classes:
        if cls.bl_space_type != "VIEW_3D":
            continue
        inst = type("P", (), {"layout": FakeLayout(log)})()
        cls.draw(inst, Ctx)
    inst = type("P", (), {"layout": FakeLayout(log)})()
    pie.PARAM_MT_pie.draw(inst, Ctx)
    panels.draw_quick_access(inst, Ctx)
    assert "param.sketch_tool" in log and "param.sketch_constrain" in log and "param.sketch_constraint_remove" in log
    assert len(log) > 60, len(log)


@test
def reregister_with_existing_trees():
    """Disabling/re-enabling (or reinstalling) must not crash with trees in the file."""
    obj = new_object("BOX")
    pd.unregister()
    pd.register()
    node(obj.param_tree, "PARAM_N_Box").inputs["Höhe"].default_value = 9
    scheduler.flush()
    approx(mesh_stats(obj)["dimensions"][2], 9)


@test
def save_and_reload_keeps_graph():
    obj = new_object("BOX")
    name = obj.name
    path = os.path.join(tempfile.mkdtemp(), "t.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    obj = bpy.data.objects[name]
    assert obj.param_tree is not None
    node(obj.param_tree, "PARAM_N_Box").inputs["Höhe"].default_value = 15
    scheduler.flush()
    approx(mesh_stats(obj)["dimensions"][2], 15)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pd.register()
    failed = 0
    try:
        for fn in TESTS:
            try:
                fn()
                print(f"ok    {fn.__name__}")
            except Exception:
                failed += 1
                print(f"FAIL  {fn.__name__}")
                traceback.print_exc()
    finally:
        pd.unregister()
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
