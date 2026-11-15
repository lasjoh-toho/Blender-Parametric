# SPDX-License-Identifier: GPL-3.0-or-later
"""Sketch editing logic in sketch coordinates, independent of mouse events.

The modal tool translates events into calls on a SketchSession; tests call the
same methods directly.
"""

import math

from ..nodes import sketch as sketch_nodes

AXIS_SNAP_ANGLE = math.radians(4)


def pressure_snap(pressure, is_tablet, toggle):
    """Snap decision from pen pressure: light = free, full = forced, between = the snap toggle."""
    if not is_tablet:
        return toggle
    if pressure >= 0.7:
        return True
    if pressure < 0.3:
        return False
    return toggle


def _seg_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 < 1e-18 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class SketchSession:
    def __init__(self, node, grid=1.0):
        self.tree_name = node.id_data.name
        self.node_name = node.name
        self.grid = grid
        self.tool = "SELECT"
        self.chain_first = None
        self.chain_last = None
        self.anchor = None  # first click of rectangle / circle / arc: (kind, data)
        self.drag_point = None
        self.dragged = False
        self.cursor = None
        self.snap_label = ""

    # -- access -------------------------------------------------------------
    @property
    def node(self):
        import bpy
        tree = bpy.data.node_groups.get(self.tree_name)
        return tree.nodes.get(self.node_name) if tree is not None else None

    def _request(self):
        from ..core import scheduler
        node = self.node
        if node is not None:
            scheduler.request(node.id_data)

    @property
    def busy(self):
        return self.chain_last is not None or self.anchor is not None

    def set_tool(self, tool):
        self.cancel()
        self.tool = tool

    def cancel(self):
        """Stop the running chain or shape. Returns True if there was one."""
        was = self.busy
        self.chain_first = self.chain_last = None
        self.anchor = None
        node = self.node
        if was and node is not None:
            node.remove_unused_points()
        return was

    # -- picking and snapping ----------------------------------------------
    def pick_point(self, x, y, radius, exclude=()):
        best, best_d = None, radius
        for i, p in enumerate(self.node.points):
            if i in exclude:
                continue
            d = math.hypot(p.x - x, p.y - y)
            if d <= best_d:
                best, best_d = i, d
        return best

    def pick_entity(self, x, y, radius):
        """Nearest line, circle or arc: ("LINE"|"CIRCLE"|"ARC", index) or None."""
        node = self.node
        pts = node.points
        best, best_d = None, radius
        for i, line in enumerate(node.lines):
            a, b = pts[line.a], pts[line.b]
            d = _seg_distance(x, y, a.x, a.y, b.x, b.y)
            if d <= best_d:
                best, best_d = ("LINE", i), d
        for i, c in enumerate(node.circles):
            d = abs(math.hypot(x - pts[c.center].x, y - pts[c.center].y) - c.radius)
            if d <= best_d:
                best, best_d = ("CIRCLE", i), d
        for i, arc in enumerate(node.arcs):
            c, s, e = pts[arc.center], pts[arc.start], pts[arc.end]
            r = math.hypot(s.x - c.x, s.y - c.y)
            a0 = math.atan2(s.y - c.y, s.x - c.x)
            sweep = (math.atan2(e.y - c.y, e.x - c.x) - a0) % (2 * math.pi) or 2 * math.pi
            am = (math.atan2(y - c.y, x - c.x) - a0) % (2 * math.pi)
            if am <= sweep:
                d = abs(math.hypot(x - c.x, y - c.y) - r)
                if d <= best_d:
                    best, best_d = ("ARC", i), d
        return best

    def snap(self, x, y, radius, snap_on, reference=None):
        """Return (x, y, point index or None, axis 'H'/'V'/None)."""
        index = self.pick_point(x, y, radius)
        if index is not None:
            p = self.node.points[index]
            self.snap_label = "Punkt"
            return p.x, p.y, index, None
        axis = None
        self.snap_label = ""
        if snap_on:
            if self.grid > 0:
                x = round(x / self.grid) * self.grid
                y = round(y / self.grid) * self.grid
                self.snap_label = "Raster"
            if reference is not None:
                dx, dy = x - reference[0], y - reference[1]
                if math.hypot(dx, dy) > 1e-9:
                    angle = abs(math.atan2(dy, dx))
                    if min(angle, math.pi - angle) < AXIS_SNAP_ANGLE:
                        y, axis = reference[1], "H"
                    elif abs(angle - math.pi / 2) < AXIS_SNAP_ANGLE:
                        x, axis = reference[0], "V"
                    if axis:
                        self.snap_label = "Horizontal" if axis == "H" else "Vertikal"
        return x, y, None, axis

    def _reference(self):
        if self.chain_last is not None:
            p = self.node.points[self.chain_last]
            return (p.x, p.y)
        if self.anchor is not None and self.anchor[0] in {"RECT", "CIRCLE"}:
            return None
        return None

    def _point_at(self, x, y, radius, snap_on, reference=None):
        x, y, index, axis = self.snap(x, y, radius, snap_on, reference)
        if index is None:
            index = self.node.add_point(x, y)
            return index, True, axis
        return index, False, None

    # -- events -------------------------------------------------------------
    def move(self, x, y, radius, snap_on):
        """Mouse moved. Returns True when the sketch changed (dragging)."""
        if self.drag_point is not None:
            sx, sy, _i, _a = self.snap(x, y, 0.0, snap_on)
            sketch_nodes.drag_targets[(self.tree_name, self.node_name)] = {self.drag_point: (sx, sy)}
            self.dragged = True
            self.cursor = (sx, sy)
            self._request()
            return True
        sx, sy, _i, _a = self.snap(x, y, radius, snap_on, self._reference())
        self.cursor = (sx, sy)
        return False

    def press(self, x, y, radius, snap_on, extend=False):
        """Left button / pen down. Returns an undo message when the sketch changed, else None."""
        node = self.node
        tool = self.tool
        if tool == "SELECT":
            index = self.pick_point(x, y, radius)
            if index is not None:
                if not extend:
                    node.clear_selection()
                node.points[index].select = not node.points[index].select if extend else True
                if not node.points[index].fixed:
                    self.drag_point = index
                    self.dragged = False
                return None
            hit = self.pick_entity(x, y, radius)
            if not extend:
                node.clear_selection()
            if hit is not None:
                coll = {"LINE": node.lines, "CIRCLE": node.circles, "ARC": node.arcs}[hit[0]]
                coll[hit[1]].select = not coll[hit[1]].select if extend else True
            return None

        if tool == "LINE":
            index, created, axis = self._point_at(x, y, radius, snap_on, self._reference())
            if self.chain_last is None:
                self.chain_first = self.chain_last = index
                return "Skizze: Punkt" if created else None
            if index == self.chain_last:
                self.cancel()
                return None
            node.add_line(self.chain_last, index)
            if axis and created:
                node.add_constraint("HORIZONTAL" if axis == "H" else "VERTICAL", (self.chain_last, index))
            closing = not created
            self.chain_last = index
            if closing:
                self.cancel()
            self._request()
            return "Skizze: Linie"

        if tool == "RECT":
            if self.anchor is None:
                sx, sy, index, _a = self.snap(x, y, radius, snap_on)
                self.anchor = ("RECT", (sx, sy, index))
                return None
            ax, ay, a_index = self.anchor[1]
            sx, sy, c_index, _a = self.snap(x, y, radius, snap_on)
            self.anchor = None
            if abs(sx - ax) < 1e-9 or abs(sy - ay) < 1e-9:
                return None
            a = a_index if a_index is not None else node.add_point(ax, ay)
            b = node.add_point(sx, ay)
            c = c_index if c_index is not None else node.add_point(sx, sy)
            d = node.add_point(ax, sy)
            for p, q in ((a, b), (b, c), (c, d), (d, a)):
                node.add_line(p, q)
            node.add_constraint("HORIZONTAL", (a, b))
            node.add_constraint("VERTICAL", (b, c))
            node.add_constraint("HORIZONTAL", (c, d))
            node.add_constraint("VERTICAL", (d, a))
            self._request()
            return "Skizze: Rechteck"

        if tool == "CIRCLE":
            if self.anchor is None:
                index, _created, _a = self._point_at(x, y, radius, snap_on)
                self.anchor = ("CIRCLE", index)
                return "Skizze: Mittelpunkt"
            center = node.points[self.anchor[1]]
            sx, sy, _i, _a = self.snap(x, y, radius, snap_on)
            r = math.hypot(sx - center.x, sy - center.y)
            index = self.anchor[1]
            self.anchor = None
            if r < 1e-9:
                return None
            node.add_circle(index, r)
            self._request()
            return "Skizze: Kreis"

        if tool == "ARC":
            if self.anchor is None:
                index, _created, _a = self._point_at(x, y, radius, snap_on)
                self.anchor = ("ARC", (index, None))
                return "Skizze: Mittelpunkt"
            center_index, start_index = self.anchor[1]
            center = node.points[center_index]
            if start_index is None:
                index, _created, _a = self._point_at(x, y, radius, snap_on)
                if index == center_index:
                    return None
                self.anchor = ("ARC", (center_index, index))
                return "Skizze: Bogenanfang"
            start = node.points[start_index]
            r = math.hypot(start.x - center.x, start.y - center.y)
            sx, sy, index, _a = self.snap(x, y, radius, snap_on)
            if index is None or index in (center_index, start_index):
                angle = math.atan2(sy - center.y, sx - center.x)
                index = node.add_point(center.x + r * math.cos(angle), center.y + r * math.sin(angle))
            node.add_arc(center_index, start_index, index)
            self.anchor = None
            self._request()
            return "Skizze: Bogen"
        return None

    def release(self):
        """Left button / pen up. Returns an undo message when a drag ended."""
        if self.drag_point is None:
            return None
        sketch_nodes.drag_targets.pop((self.tree_name, self.node_name), None)
        self.drag_point = None
        if self.dragged:
            self.dragged = False
            self._request()
            return "Skizze: Punkt verschieben"
        return None

    def preview(self):
        """Rubber-band shapes for the overlay: list of polylines in sketch coordinates."""
        if self.cursor is None:
            return []
        node = self.node
        cx, cy = self.cursor
        if self.tool == "LINE" and self.chain_last is not None:
            p = node.points[self.chain_last]
            return [[(p.x, p.y), (cx, cy)]]
        if self.anchor is None:
            return []
        kind, data = self.anchor
        if kind == "RECT":
            ax, ay, _i = data
            return [[(ax, ay), (cx, ay), (cx, cy), (ax, cy), (ax, ay)]]
        if kind == "CIRCLE":
            c = node.points[data]
            r = math.hypot(cx - c.x, cy - c.y)
            return [[(c.x + r * math.cos(math.tau * i / 48), c.y + r * math.sin(math.tau * i / 48)) for i in range(49)]]
        if kind == "ARC":
            c = node.points[data[0]]
            if data[1] is None:
                return [[(c.x, c.y), (cx, cy)]]
            s = node.points[data[1]]
            r = math.hypot(s.x - c.x, s.y - c.y)
            a0 = math.atan2(s.y - c.y, s.x - c.x)
            sweep = (math.atan2(cy - c.y, cx - c.x) - a0) % math.tau or math.tau
            return [[(c.x + r * math.cos(a0 + sweep * i / 32), c.y + r * math.sin(a0 + sweep * i / 32)) for i in range(33)]]
        return []
