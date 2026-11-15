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
    ctx = bpy.context
    bpy.ops.param.setup_units()
    obj = new_object("BOX")
    bpy.ops.param.print_check()
    report = ctx.scene["param_print_report"]
    assert report.startswith("Druckbereit"), report
    assert "20.00 × 20.00 × 20.00 mm" in report, report
    path = os.path.join(tempfile.mkdtemp(), "box.stl")
    bpy.ops.param.export_stl(filepath=path)
    assert os.path.getsize(path) == 84 + 50 * 12, os.path.getsize(path)


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
