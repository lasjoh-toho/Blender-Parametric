# Parametric Design für Blender

Parametrisch modellieren und für den 3D-Druck vorbereiten: Werkzeuge im 3D-Viewport
legen automatisch Nodes in einem eigenen Node-Graph an. Ändert man einen Wert – im Graph,
im Seitenpanel oder über einen benannten Parameter –, baut sich das Objekt sofort neu auf.

*Parametric modelling for Blender: viewport tools create nodes in a live graph; change a
value and the model rebuilds. Made for 3D printing (mm units, print check, STL export).*

- **Blender:** 4.2 LTS oder neuer (Extension-Format)
- **Version:** 0.1.0 · [Konzept](docs/KONZEPT.md) · [Änderungen](CHANGELOG.md)

## Installation

1. Die Datei `parametric_design-0.1.0.zip` aus den [Releases](https://github.com/lasjoh-toho/blender-parametric/releases) laden.
2. In Blender: *Bearbeiten → Einstellungen → Get Extensions → ⌄ (oben rechts) → Install from Disk…* und die ZIP wählen.
3. Im 3D-Viewport mit `N` das Seitenpanel öffnen, Reiter **Parametric**.

## Erste Schritte

1. **mm** klicken (Szene auf Millimeter) und **Arbeitsbereich** klicken (Viewport oben, Node-Graph unten).
2. Ein Werkzeug wählen, z. B. **Box**. Es entsteht ein Objekt *Param Box* mit Graph `Box → Output`.
3. Bei ausgewähltem Objekt weitere Werkzeuge benutzen: **Bevel**, **Array**, **Boolean** … – jedes fügt einen Node vor dem Output ein. Grundkörper und Profile werden zum Objekt hinzugefügt (an der Position des 3D-Cursors).
4. Unter **Parameter** einen Wert des aktiven Nodes mit dem Driver-Symbol zum benannten Parameter machen. Parameter lassen sich in Formeln verwenden, z. B. `breite / 2`.
5. **3D-Druck → Druck-Check**, dann **STL** exportieren.

Radialmenü (Stift/Schnellzugriff): **Umschalt+Alt+Q** im 3D-Viewport und Node-Editor.
Die Taste lässt sich in den Add-on-Einstellungen ändern; Stift-Seitentasten legt man in den
Tablet-Einstellungen des Systems auf diese Kombination.

## Was drin ist (0.1)

| Bereich | Werkzeuge / Nodes |
|---|---|
| Grundkörper | Box, Zylinder, Kugel, Kegel |
| Kurven & Skizze | Rechteck (mit Eckradius), Kreis, Polygon, Polylinie → Extrudieren oder Rotieren |
| Operationen | Boolean (Differenz/Vereinigung/Schnitt), Bevel/Fase, Shell, Spiegeln, Zusammenfügen |
| Modifier | Verschieben/Rotieren/Skalieren, Soften (Subdivision), lineares und radiales Array |
| Parameter | Länge, Winkel, Zahl, Formel, Vektor, Objekt-Eingang (Link) |
| Struktur | Gruppe (Untergraph mit exponierten Parametern), Output |
| Sync | Live, Sync aufheben, Re-link, Bake, Dirty-/Fehleranzeige |
| Objekte | Duplizieren (unabhängig), Instanz (geteilter Graph), Gruppieren |
| Druck | Maße in mm, Volumen, offene Kanten, STL-Export in mm |

Formeln: `+ - * / // % **`, Vergleiche, `a if b else c`, Funktionen `sin cos tan asin acos atan atan2`
(in Grad), `sqrt abs min max round floor ceil log exp clamp`, Konstanten `pi e tau`.

Noch nicht enthalten (siehe [Roadmap](docs/KONZEPT.md#8-roadmap)): freie Skizze mit
geometrischen Constraints, druckabhängiger Snap, Array entlang Pfad, 3MF.

## Entwicklung

```bash
pip install bpy==5.3.0          # Blender als Python-Modul (Python 3.13)
python tests/run_tests.py       # headless Tests
python scripts/build_extension.py   # ZIP nach dist/
```

Mit einer Blender-Installation geht auch `blender -b --factory-startup --python tests/run_tests.py`.

Lizenz: GPL-3.0-or-later
