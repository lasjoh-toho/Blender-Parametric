# SPDX-License-Identifier: GPL-3.0-or-later
"""Debounced re-evaluation and dependencies between parametric objects."""

import bpy
from bpy.app.handlers import persistent

from . import evaluator
from .evaluator import TREE_ID

DELAY = 0.03
_pending = set()
_suspended = [0]


class suspended:
    """Context manager: collect changes without evaluating (used by tools that add many nodes)."""

    def __enter__(self):
        _suspended[0] += 1

    def __exit__(self, *exc):
        _suspended[0] -= 1


def parametric_trees():
    return [t for t in bpy.data.node_groups if t.bl_idname == TREE_ID]


def request(tree):
    if tree is None or evaluator.state["evaluating"]:
        return
    try:
        tree.param_dirty = True
    except AttributeError:
        return
    _pending.add(tree.name)
    if _suspended[0]:
        return
    if bpy.app.background:
        # No event loop in background mode: evaluate right away.
        flush()
        return
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=DELAY)


def _timer():
    flush()
    return None


def dependents(tree):
    """Trees that use ``tree`` as a group or read one of its output objects."""
    targets = {o.target for o in evaluator.output_nodes(tree) if o.target is not None}
    result = []
    for other in parametric_trees():
        if other == tree:
            continue
        for node in other.nodes:
            if node.bl_idname == "PARAM_N_Group" and node.subtree == tree:
                result.append(other)
                break
            if node.bl_idname == "PARAM_N_ObjectInput" and node.source is not None and node.source in targets:
                result.append(other)
                break
    return result


def flush():
    """Evaluate all pending trees, then whatever depends on them (once each)."""
    done = set()
    rounds = 0
    while _pending and rounds < 32:
        rounds += 1
        names = list(_pending)
        _pending.clear()
        for name in names:
            if name in done:
                continue
            tree = bpy.data.node_groups.get(name)
            if tree is None or tree.bl_idname != TREE_ID:
                continue
            done.add(name)
            evaluator.evaluate_tree(tree)
            for dep in dependents(tree):
                if dep.name not in done:
                    dep.param_dirty = True
                    _pending.add(dep.name)
    _pending.clear()
    _redraw()


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "NODE_EDITOR"}:
                area.tag_redraw()


@persistent
def _on_depsgraph_update(scene, depsgraph):
    """Re-evaluate trees whose object inputs moved relative to their owner."""
    if evaluator.state["evaluating"]:
        return
    moved = set()
    for update in depsgraph.updates:
        if not update.is_updated_transform:
            continue
        idb = update.id
        if isinstance(idb, bpy.types.Object) and not idb.name.startswith("_param_tmp"):
            moved.add(idb.original.name)
    if not moved:
        return
    for tree in parametric_trees():
        owners = {o.target.name for o in evaluator.output_nodes(tree) if o.target is not None}
        for node in tree.nodes:
            if node.bl_idname != "PARAM_N_ObjectInput" or node.source is None or not node.relative:
                continue
            if node.source.name in moved or (owners & moved):
                request(tree)
                break


@persistent
def _on_load(_dummy):
    _pending.clear()


def register():
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    _pending.clear()
