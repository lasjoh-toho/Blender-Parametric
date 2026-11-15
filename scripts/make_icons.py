# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the two-colour tool icons as SVG (docs/icons) and write the list
for the PNG renderer (scripts/render_icons.js).

Every icon is drawn on a 32 x 32 grid. BASE strokes show the context, ACCENT
strokes show the element the tool acts on.

Usage: python scripts/make_icons.py && node scripts/render_icons.js
"""

import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_DIR = os.path.join(ROOT, "docs", "icons")

BASE = "#DADADA"
ACCENT = "#3DDBA8"


def b(d, dash=False):
    return ("path", d, BASE, "none", dash)


def a(d, dash=False):
    return ("path", d, ACCENT, "none", dash)


def af(d):
    """Accent outline with a translucent accent fill."""
    return ("path", d, ACCENT, ACCENT, False)


def dot(x, y, r=2.2, color=ACCENT):
    return ("dot", (x, y, r), color, color, False)


def rect(x, y, w, h, r=0):
    if r:
        return (f"M{x + r} {y} H{x + w - r} Q{x + w} {y} {x + w} {y + r} V{y + h - r} Q{x + w} {y + h} {x + w - r} {y + h} "
                f"H{x + r} Q{x} {y + h} {x} {y + h - r} V{y + r} Q{x} {y} {x + r} {y} Z")
    return f"M{x} {y} H{x + w} V{y + h} H{x} Z"


def circle(cx, cy, r):
    return f"M{cx - r} {cy} A{r} {r} 0 1 0 {cx + r} {cy} A{r} {r} 0 1 0 {cx - r} {cy} Z"


def ellipse(cx, cy, rx, ry):
    return f"M{cx - rx} {cy} A{rx} {ry} 0 1 0 {cx + rx} {cy} A{rx} {ry} 0 1 0 {cx - rx} {cy} Z"


def ngon(cx, cy, r, n, start=-90):
    pts = [(cx + r * math.cos(math.radians(start + 360 * i / n)), cy + r * math.sin(math.radians(start + 360 * i / n))) for i in range(n)]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


ARROWS4 = "M16 2 V9 M13 5 L16 2 L19 5 M16 30 V23 M13 27 L16 30 L19 27 M2 16 H9 M5 13 L2 16 L5 19 M30 16 H23 M27 13 L30 16 L27 19"
LINK_L = rect(3, 11, 9, 10, 2)
LINK_R = rect(20, 11, 9, 10, 2)

ICONS = {
    # primitives
    "box": [b("M5 10 V22 L16 28 L27 22 V10 M16 16 V28"), af("M16 4 L27 10 L16 16 L5 10 Z")],
    "cylinder": [b("M6 8 V24 A10 4 0 0 0 26 24 V8"), af(ellipse(16, 8, 10, 4))],
    "sphere": [b(circle(16, 16, 11)), a("M5 16 A11 4.5 0 0 0 27 16"), a("M5 16 A11 4.5 0 0 1 27 16", dash=True)],
    "cone": [b("M16 4 L6 24 M16 4 L26 24"), af(ellipse(16, 24, 10, 4))],
    # profiles
    "rectangle": [af(rect(4, 8, 24, 16, 3))],
    "circle": [af(circle(16, 16, 11))],
    "polygon": [af(ngon(16, 16, 12, 6))],
    "polyline": [af("M5 26 V13 L14 5 L27 11 V26 Z"), dot(5, 26, 2, BASE), dot(5, 13, 2, BASE), dot(14, 5, 2, BASE), dot(27, 11, 2, BASE), dot(27, 26, 2, BASE)],
    # operations
    "extrude": [b("M5 24 L16 28 L27 24 L16 20 Z"), a("M16 20 V5 M11 10 L16 5 L21 10")],
    "revolve": [b("M16 3 V29", dash=True), b("M20 9 H27 V23 H20 Z"), a("M12 12 A7 3.2 0 1 0 12 20 M8.5 22.5 L12.5 20 L10 16.5")],
    "transform": [b(rect(12, 12, 8, 8, 1)), a(ARROWS4)],
    "bevel": [b("M26 15 V26 H6 V6 H17"), a("M17 6 Q26 6 26 15")],
    "smooth": [b("M6 25 L9 9 L23 6 L27 23 Z", dash=True), a(ellipse(16.5, 16, 9, 8.5))],
    "shell": [b(rect(4, 4, 24, 24, 4)), af(rect(10, 10, 12, 12, 2))],
    "mirror": [b("M13 7 V25 H4 Z"), b("M16 3 V29", dash=True), af("M19 7 V25 H28 Z")],
    "array_linear": [b(rect(2, 12, 7, 8, 1)), af(rect(12.5, 12, 7, 8, 1)), af(rect(23, 12, 7, 8, 1))],
    "array_radial": [b(circle(16, 6, 3.2))] + [af(circle(16 + 10 * math.sin(math.radians(60 * i)), 16 - 10 * math.cos(math.radians(60 * i)), 3.2)) for i in range(1, 6)],
    "bool_difference": [b("M4 4 H20 V12 A8 8 0 0 0 12 20 H4 Z"), a(circle(20, 20, 8), dash=True)],
    "bool_union": [b(rect(4, 4, 16, 16)), af(circle(20, 20, 8))],
    "bool_intersect": [b(rect(4, 4, 16, 16)), b(circle(20, 20, 8)), af("M20 12 A8 8 0 0 0 12 20 H20 Z")],
    # structure
    "duplicate": [b(rect(4, 4, 16, 16, 2)), af(rect(12, 12, 16, 16, 2))],
    "instance": [b(rect(4, 4, 14, 14, 2)), a(rect(14, 14, 14, 14, 2), dash=True), a("M11 11 L21 21")],
    "group": [b(rect(8, 8, 8, 8, 1)), b(circle(21, 21, 4)), a(rect(3, 3, 26, 26, 4), dash=True)],
    # sync
    "sync": [b(LINK_L), b(LINK_R), a("M12 16 H20 M17 13 L20 16 L17 19")],
    "unsync": [b(LINK_L), b(LINK_R), a("M12 16 H14 M18 16 H20 M13.5 23 L18.5 9")],
    "relink": [b(LINK_L), b(LINK_R), a("M13 16 H19 M15 13.5 L12.5 16 L15 18.5 M17 13.5 L19.5 16 L17 18.5")],
    "bake": [b("M16 2 V9 M12.5 6 L16 9.5 L19.5 6"), af("M6 16 L16 12 L26 16 V25 L16 29 L6 25 Z"), a("M6 16 L16 20 L26 16 M16 20 V29")],
    "recalc": [a("M26 16 A10 10 0 1 1 22 8 M22 3 V8.5 H16.5")],
    # parameters
    "param_length": [b("M5 9 V23 M27 9 V23"), a("M6 16 H26 M10 12.5 L6 16 L10 19.5 M22 12.5 L26 16 L22 19.5")],
    "param_angle": [b("M5 26 H27 M5 26 L20 6"), a("M20 26 A15 15 0 0 0 14 14")],
    "param_number": [b("M4 8 H28 M4 16 H28 M4 24 H28"), dot(11, 8, 3), dot(21, 16, 3), dot(14, 24, 3)],
    "formula": [a("M17 5 Q12 4 11 10 L8 27 M6 13 H15"), b("M18 15 L27 26 M27 15 L18 26")],
    # print
    "print_check": [b("M4 27 H28 M10 27 V16 H22 V27"), a("M10 8 L14.5 12.5 L23 3.5")],
    "export": [b("M5 20 V27 H27 V20"), a("M16 21 V5 M10 11 L16 5 L22 11")],
    # workspace / quick access
    "snap": [b("M8 5 V17 A8 8 0 0 0 24 17 V5"), a("M5 5 H11 M21 5 H27 M5 10 H11 M21 10 H27")],
    "workspace": [b(rect(4, 4, 24, 24, 3)), a("M4 18 H28"), a("M9 23 H13 M17 23 H21")],
    "units": [b(rect(3, 11, 26, 10, 2)), a("M9 11 V16 M15 11 V18 M21 11 V16")],
    "undo": [a("M12 6 L5 13 L12 20 M5 13 H20 A6.5 6.5 0 0 1 20 26 H13")],
    # sketch tools
    "sketch": [b("M7 25 L9 18 L21 6 L26 11 L14 23 Z M18 9 L23 14"), a("M4 28 H16")],
    "sketch_select": [af("M9 4 V23 L14 18.5 L17.5 27 L21 25.5 L17.5 17.5 H24 Z")],
    "sketch_line": [a("M7 25 L25 7"), dot(7, 25, 3, BASE), dot(25, 7, 3, BASE)],
    "sketch_rect": [af(rect(5, 8, 22, 16)), dot(5, 24, 3, BASE), dot(27, 8, 3, BASE)],
    "sketch_circle": [af(circle(16, 16, 11)), b("M16 16 L24 8.5"), dot(16, 16, 2.6, BASE)],
    "sketch_arc": [b("M7 26 L26 26 M7 26 L7 7", dash=True), a("M26 26 A19 19 0 0 0 7 7"), dot(7, 26, 2.6, BASE)],
    "delete": [a("M9 9 L23 23 M23 9 L9 23"), b(rect(4, 4, 24, 24, 4), dash=True)],
    "construction": [b("M5 26 L27 6", dash=True), a("M5 12 H13 M9 8 V16")],
    # constraints: the lines are the context, the relation is the accent
    "con_coincident": [b("M5 26 L16 16 L27 25"), dot(16, 16, 3.6)],
    "con_horizontal": [b("M5 23 L27 9", dash=True), a("M5 16 H27")],
    "con_vertical": [b("M9 5 L23 27", dash=True), a("M16 5 V27")],
    "con_distance": [b("M5 9 V23 M27 9 V23"), a("M6 16 H26 M10 12.5 L6 16 L10 19.5 M22 12.5 L26 16 L22 19.5")],
    "con_parallel": [b("M5 24 L19 6"), a("M13 26 L27 8")],
    "con_perpendicular": [b("M5 25 H27 M16 20 H21 V25"), a("M16 25 V6")],
    "con_equal": [b("M5 8 H27 M5 24 H27"), a("M12 13.5 H20 M12 18.5 H20")],
    "con_angle": [b("M5 26 H27 M5 26 L20 6"), a("M20 26 A15 15 0 0 0 14 14")],
    "con_fix": [b("M11 14 V10 A5 5 0 0 1 21 10 V14"), af(rect(7, 14, 18, 13, 3))],
    "con_tangent": [b(circle(14, 19, 8)), a("M3 11 H29")],
    "con_midpoint": [b("M5 25 L27 7"), dot(16, 16, 3.6), b("M3 20 L8 26 M24 5 L29 11")],
    "con_on_line": [b("M4 26 L28 6"), dot(20.5, 12.2, 3.6)],
    "con_radius": [b(circle(16, 16, 11)), a("M16 16 L23.8 8.2 M19 8.5 H23.8 V13"), dot(16, 16, 2.4, BASE)],
    "con_on_curve": [b(circle(15, 17, 10)), dot(22.1, 9.9, 3.6)],
}


def svg(shapes):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" fill="none" '
           'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">']
    for kind, data, stroke, fill, dash in shapes:
        dash_attr = ' stroke-dasharray="2.5 3.5"' if dash else ""
        fill_attr = f' fill="{fill}" fill-opacity="{1 if kind == "dot" else 0.28}"' if fill != "none" else ""
        if kind == "dot":
            x, y, r = data
            out.append(f'  <circle cx="{x}" cy="{y}" r="{r}" stroke="none"{fill_attr}/>')
        else:
            out.append(f'  <path d="{data}" stroke="{stroke}"{fill_attr}{dash_attr}/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    os.makedirs(SVG_DIR, exist_ok=True)
    for name, shapes in ICONS.items():
        with open(os.path.join(SVG_DIR, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg(shapes))
    print(f"{len(ICONS)} icons -> {SVG_DIR}")


if __name__ == "__main__":
    main()
