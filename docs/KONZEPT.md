# Parametric Design für Blender – Konzept (überarbeitet)

Stand: 15.11.2026 · Version des Konzepts: 2 · Zielversion des Plugins: 0.1.0

Dieses Dokument überarbeitet das ursprüngliche Konzept (Werkzeug-Toolbox, Modifier,
Duplicate/Array, Sync, Snap, Group, Stylus-Bedienung) und legt fest, was in die erste
installierbare Version kommt und was später folgt.

Die Skizzen der Oberfläche aus dem ursprünglichen Konzept liegen unter
[mockups/](mockups/README.md) (Arbeitsbereich, Werkzeug-Übersicht, Snap/Group/Stift).

## 1. Ziel

Ein Blender-Plugin, mit dem man Objekte **parametrisch modelliert und für den 3D-Druck
vorbereitet**. Man arbeitet mit Werkzeugen im 3D-Viewport (Würfel, Zylinder, Profile,
Extrudieren, Bevel, Array, Boolean …). Jeder Werkzeugschritt erzeugt automatisch einen
Node in einem eigenen Node-Graph. Ändert man einen Wert im Node-Graph oder im
Seitenpanel, baut sich das Objekt sofort neu auf.

**Kernprinzip:** Werkzeug benutzen → Node entsteht. Node-Wert ändern → Modell aktualisiert sich.

Gewählter Ansatz aus dem ursprünglichen Gespräch: *eigenes Node-System* (kein
Geometry-Nodes-Graph als Benutzeroberfläche) plus *Parameter als Node-Eingänge*.

## 2. Technische Grundlage (aktualisiert)

| Thema | Entscheidung |
|---|---|
| Blender-Version | **4.2 LTS bis 5.x**. Getestet mit 5.3 (headless) und der Version auf Jos Mac. |
| Paketformat | **Blender Extension** (`blender_manifest.toml`, Installation per ZIP über *Einstellungen → Get Extensions → Install from Disk*). Kein altes `bl_info`. |
| Lizenz | GPL-3.0-or-later (Pflicht für Blender-Extensions mit Python-Code). |
| Abhängigkeiten | Keine externen Wheels. Nur `bpy`, `bmesh`, `mathutils`, `gpu`, `blf`. |
| Node-System | Eigener `NodeTree`-Typ **„Parametric Tree“** mit eigenen Sockets (Geometrie, Länge, Winkel, Zahl, Ganzzahl, Vektor). |
| Geometrie-Kern | Auswertung in Python mit `bmesh`. Operationen, die `bmesh` nicht bietet (Boolean, Smooth/Subdivision, Shell), laufen über Blenders eigene Modifier auf einem kurzlebigen Hilfsobjekt. |
| Auswertung | Änderungen markieren Nodes als *dirty*; ein entprellter Timer wertet den Graph neu aus und schreibt das Ergebnis in das Mesh des Zielobjekts. |
| Einheiten | Für den Druck wird die Szene auf **Millimeter** umgestellt (1 Blender-Einheit = 1 mm). |

Warum kein Geometry-Nodes-Backend? GN wäre schneller, aber dann würden zwei Graphen
parallel gepflegt, und die GN-Python-API ändert sich zwischen 4.x und 5.x deutlich. Der
eigene Python-Kern ist für typische Druckteile schnell genug und bleibt stabil. Ein
späterer Wechsel des Backends ist möglich, weil die Nodes nur über eine schmale
Schnittstelle (`evaluate(ctx)`) mit dem Kern sprechen.

## 3. Arbeitsbereich

Operator **„Parametrischer Arbeitsbereich“** teilt den aktuellen 3D-Viewport: oben das
3D-Modell, unten der Node-Editor mit dem Graph des aktiven Objekts. Dazu:

- **Toolbox** im Seitenpanel des 3D-Viewports (Reiter *Parametric*), Buttons in 44-px-Höhe,
  stift- und fingertauglich.
- **Node-Graph** im Node-Editor (Reiter *Parametric* in dessen Seitenpanel für Status/Sync).
- **Parameter-Anzeige** direkt im Viewport: benannte Parameter des aktiven Objekts werden
  als Badges neben dem Objekt eingeblendet.

## 4. Werkzeuge

Status: ✅ in 0.1 · 🔜 später geplant

### 4.1 Grundkörper
- ✅ Box (Breite, Tiefe, Höhe)
- ✅ Zylinder (Radius, Höhe, Segmente)
- ✅ Kugel (Radius, Segmente, Ringe)
- ✅ Kegel (Radius unten, Radius oben, Höhe, Segmente)

### 4.2 Kurven & Skizze
- ✅ Rechteck-Profil (Breite, Höhe, Eckradius)
- ✅ Kreis-Profil (Radius, Segmente)
- ✅ Polygon-Profil (Radius, Ecken)
- ✅ Polylinie (Punktliste `x,y; x,y; …`, Werte können Parameter-Namen und Formeln enthalten)
- 🔜 Freie Skizze im Viewport: Linie, Bogen/Radius, Spline mit Fang und Stiftdruck
- 🔜 Geometrische Constraints auf der Skizze (siehe 4.5)

### 4.3 Operationen
- ✅ Extrudieren (Profil → Körper, Höhe)
- ✅ Rotieren/Revolve (Profil → Drehkörper, Winkel, Segmente)
- ✅ Boolean (Vereinigung, Differenz, Schnitt) zwischen zwei Geometrien oder mit einem anderen parametrischen Objekt
- ✅ Bevel / Fase (Breite, Segmente; 1 Segment = Fase, mehr = Rundung)
- ✅ Shell / Wandstärke (Dicke)
- ✅ Spiegeln (Achse, optional verschmelzen)
- 🔜 Fillet einzelner, ausgewählter Kanten (0.1 bevelt alle Kanten bzw. nach Winkel)

### 4.4 Modifier (nicht destruktiv, als Nodes)
- ✅ Verschieben, Rotieren, Skalieren (ein Transform-Node)
- ✅ Bevel (siehe oben, mit Winkelgrenze)
- ✅ Soften/Smooth (Subdivision-Stufe)
- ✅ Lineares Array (Anzahl, Versatz)
- ✅ Radiales Array (Anzahl, Achse, Gesamtwinkel)
- 🔜 Array entlang Pfad, Scatter

### 4.5 Constraints
In 0.1 werden **Maß-Constraints** über Parameter umgesetzt: jede Länge, jeder Winkel und
jeder Radius ist ein Node-Eingang und kann an einen benannten Parameter oder eine Formel
gebunden werden (z. B. `Höhe = Breite / 2`).

🔜 **Geometrische Constraints** (Distanz, Winkel, Tangente, Parallel, Senkrecht, Gleich,
Fix, Kolinear) brauchen einen Constraint-Solver für Skizzen. Geplant für 0.2: eigener
numerischer Solver (Gauß-Newton mit `mathutils`/`numpy`) oder Anbindung an den Solver von
CAD Sketcher. Das ist der größte offene Baustein und bewusst aus 0.1 herausgenommen, damit
die erste Version stabil installierbar ist.

### 4.6 Parameter
- ✅ Parameter-Node (Name, Wert, Einheit Länge/Winkel/Zahl), sichtbar im Seitenpanel
- ✅ Formel-Node (Ausdruck mit Eingängen `a`–`d` und Zugriff auf alle Parameter-Namen; sicher ausgewertet, nur Mathematik)
- ✅ Objekt-Eingang (Link): Geometrie eines anderen parametrischen Objekts verwenden
- 🔜 Tabellen-Parameter (Varianten, z. B. Größen S/M/L)
- 🔜 Blender-Driver auf Parameter

### 4.7 Duplicate, Instance, Group
- ✅ **Duplizieren**: kopiert Objekt *und* Graph – danach unabhängig.
- ✅ **Instanz**: neues Objekt mit geteiltem Mesh und Graph, nur der Transform ist eigen. Änderungen am Graph wirken auf alle Instanzen.
- ✅ **Gruppe**: Group-Node, der einen anderen Parametric Tree als Untergraph einbindet. Parameter, die im Untergraph als *exponiert* markiert sind, erscheinen als Eingänge des Group-Nodes. Bearbeiten in place: *Gruppe öffnen* springt im Node-Editor in den Untergraph.
- 🔜 Gruppen sperren/verstecken als eigener Status (bis dahin über Blenders Collections)

### 4.8 Sync & Status
Pro Objekt (am Output-Node):
- ✅ **Sync (live)**: jede Änderung baut das Modell neu auf.
- ✅ **Sync aufheben (einfrieren)**: Graph bleibt erhalten, Mesh wird nicht mehr aktualisiert.
- ✅ **Re-link**: wieder auf live schalten und sofort neu berechnen.
- ✅ **Bake**: Graph vom Objekt lösen, es bleibt ein normales Mesh.
- ✅ **Dirty-Anzeige**: veraltete Nodes werden markiert, Fehler werden am Node angezeigt.
- ✅ **History**: über Blenders Undo (jede Werkzeugaktion ist ein Undo-Schritt).

## 5. Bedienkonzept

### 5.1 Snap
Blender hat bereits ein vollständiges Fangsystem. Das Plugin erfindet es nicht neu, sondern
macht es schnell erreichbar:
- ✅ Snap an/aus und Snap-Ziele (Vertex, Kante, Kantenmitte, Fläche, Raster/Inkrement) im Panel und im Radialmenü
- ✅ Anzeige des Snap-Status im Viewport-Badge
- 🔜 Druckabhängiger Snap (leichter Druck = frei, voller Druck = Snap) – braucht das Skizzen-Werkzeug aus 4.2, weil Blender den Stiftdruck nur in eigenen modalen Werkzeugen liefert

### 5.2 Stift und Schnellzugriff
- ✅ **Radialmenü** (Pie) mit 8 Schnellzugriffen: Box, Zylinder, Extrudieren, Bevel, Array, Boolean-Differenz, Snap, Sync. Standardtaste **Umschalt+Alt+Q** im 3D-Viewport und Node-Editor, frei belegbar in den Add-on-Einstellungen. Stift-Seitentasten legt man in den Tablet-Einstellungen des Systems auf diese Taste.
- ✅ Große Buttons (44 px) in der Toolbox
- ✅ Wert-Eingabe per Doppelklick/Doppeltippen auf jedes Feld (Blender-Standard)
- 🔜 Gesten (Halten an der Stiftspitze öffnet das Menü am Cursor) im Skizzen-Werkzeug

## 6. 3D-Druck
- ✅ Druck-Check im Panel: Maße in mm, Volumen, nicht-manifolde Kanten, lose Teile
- ✅ STL-Export des aktiven Objekts (ausgewertetes Mesh, in mm)
- 🔜 3MF-Export, Mindestwandstärke-Prüfung, Überhang-Anzeige

## 7. Architektur

```
parametric_design/
  blender_manifest.toml
  __init__.py          Registrierung
  preferences.py       Add-on-Einstellungen, Tastenbelegung
  props.py             Object.param_tree, Szene-Einstellungen
  core/
    expressions.py     sichere Formel-Auswertung
    geometry.py        bmesh-Bausteine (Primitive, Profile, Extrude, Array …)
    modifier_ops.py    Boolean/Subdivision/Shell über Hilfsobjekt
    evaluator.py       Graph-Auswertung, Fehler, Dirty-Status
    scheduler.py       entprellte Neuberechnung, Abhängigkeiten zwischen Objekten
  nodes/
    tree.py            Parametric Tree
    sockets.py         Socket-Typen
    base.py            Basisklasse der Nodes
    *.py               Node-Kategorien
  ops/                 Werkzeuge (Viewport), Sync/Bake, Duplizieren, Arbeitsbereich, Druck
  ui/                  Panels, Radialmenü, Viewport-Overlay
tests/                 headless Tests mit dem bpy-Modul
```

## 8. Roadmap
- **0.1** (diese Version): Node-System, alle ✅-Werkzeuge, Sync/Bake, Gruppen, Radialmenü, Druck-Check und STL-Export.
- **0.2**: Skizzen-Werkzeug im Viewport mit geometrischen Constraints und Solver, druckabhängiger Snap.
- **0.3**: Array entlang Pfad, Tabellen-Parameter, 3MF-Export, Überhang- und Wandstärke-Analyse.
