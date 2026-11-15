# Parametric Design für Blender

Parametrisch modellieren und für den 3D-Druck vorbereiten: Werkzeuge im 3D-Viewport
legen automatisch Nodes in einem eigenen Node-Graph an. Ändert man einen Wert – im Graph,
im Seitenpanel oder über einen benannten Parameter –, baut sich das Objekt sofort neu auf.

*Parametric modelling for Blender: viewport tools create nodes in a live graph; change a
value and the model rebuilds. Made for 3D printing (mm units, print check, STL export).*

- **Blender:** 4.2 LTS oder neuer (Extension-Format)
- **Version:** 0.2.0 · [Konzept](docs/KONZEPT.md) · [Änderungen](CHANGELOG.md)

## Installation

1. Die Datei `parametric_design-0.2.0.zip` aus den [Releases](https://github.com/lasjoh-toho/blender-parametric/releases) laden.
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

## Was drin ist (0.2)

| Bereich | Werkzeuge / Nodes |
|---|---|
| Grundkörper | Box, Zylinder, Kugel, Kegel |
| Skizze | Linie, Bogen, Kreis, Rechteck frei im Viewport zeichnen, Punkte ziehen, Hilfslinien; 13 Constraints (Distanz, Winkel, Tangente, Parallel, Senkrecht, Gleich, Fix, Kolinear, Horizontal, Vertikal, Deckungsgleich, Mittelpunkt, Radius) mit Solver |
| Fertige Profile | Rechteck (mit Eckradius), Kreis, Polygon, Polylinie → Extrudieren oder Rotieren |
| Operationen | Boolean (Differenz/Vereinigung/Schnitt), Bevel/Fase, Shell, Spiegeln, Zusammenfügen |
| Modifier | Verschieben/Rotieren/Skalieren, Soften (Subdivision), lineares und radiales Array |
| Parameter | Länge, Winkel, Zahl, Formel, Vektor, Objekt-Eingang (Link) |
| Struktur | Gruppe (Untergraph mit exponierten Parametern), Output |
| Sync | Live, Sync aufheben, Re-link, Bake, Dirty-/Fehleranzeige |
| Objekte | Duplizieren (unabhängig), Instanz (geteilter Graph), Gruppieren |
| Druck | Maße in mm, Volumen, offene Kanten, STL-Export in mm |

Formeln: `+ - * / // % **`, Vergleiche, `a if b else c`, Funktionen `sin cos tan asin acos atan atan2`
(in Grad), `sqrt abs min max round floor ceil log exp clamp`, Konstanten `pi e tau`.

### Skizzieren

1. In **Kurven & Skizze** auf **Linie** tippen. Ohne aktives parametrisches Objekt entsteht ein neues (`Skizze → Extrudieren → Output`).
2. Punkte in den Viewport setzen. Ein Klick auf den Startpunkt schließt die Kontur, und das Objekt entsteht. `Esc` oder `Enter` beendet eine Form, `Esc` noch einmal das Werkzeug.
3. Mit **Auswahl** Linien oder Punkte antippen (Umschalt für mehrere) und unter **Constraints** z. B. **Distanz** setzen. In der Liste *Aktive Constraints* den Wert ändern oder im Formelfeld einen Parameter eintragen, etwa `breite / 2`.
4. Die Statuszeile zeigt, ob die Skizze voll bestimmt ist oder wie viele Freiheitsgrade offen sind.

Snap: Punkte fangen immer aufeinander. Raster und Horizontal/Vertikal greifen, wenn Snap an ist (Strg kehrt es um). Mit dem Stift: leichter Druck zeichnet frei, fester Druck erzwingt den Snap.

Noch nicht enthalten (siehe [Roadmap](docs/KONZEPT.md#8-roadmap)): Spline, Fillet einzelner Kanten,
Array entlang Pfad, 3MF.

## Entwicklung

```bash
pip install bpy==5.3.0          # Blender als Python-Modul (Python 3.13)
python tests/test_solver.py     # Solver-Tests (nur numpy)
python tests/run_tests.py       # headless Tests
python scripts/build_extension.py   # ZIP nach dist/
python scripts/make_icons.py && node scripts/render_icons.js   # Icons neu erzeugen (braucht Playwright)
```

Mit einer Blender-Installation geht auch `blender -b --factory-startup --python tests/run_tests.py`.

Lizenz: GPL-3.0-or-later
