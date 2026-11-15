# Änderungen

## 0.2.0

- Freie Skizze im Viewport: Linie, Bogen, Kreis, Rechteck, Auswahl, Punkte ziehen, Hilfslinien, Löschen
- Constraint-Solver mit 13 Constraints; Anzeige von Freiheitsgraden und Konflikten
- Maß-Constraints nehmen Parameter-Namen und Formeln an; Liste „Aktive Constraints“
- Snap im Skizzen-Werkzeug auf Punkte, Raster und Achsen, gesteuert über Stiftdruck oder Snap-Schalter
- Skizze mit Maßen wird im Viewport eingeblendet
- 60 eigene zweifarbige Icons: die Akzentfarbe zeigt das Element, auf das die Funktion wirkt
- Toolbox aus quadratischen Kacheln mit großen Icons, Kategorien wie im Mockup
- Schnellzugriff-Leiste oben im Viewport; Radialmenü belegt wie im Mockup
- Maße in der Skizze nutzen die Einheit der Szene; derselbe Constraint wird nicht doppelt angelegt
- Behoben: Absturz beim erneuten Aktivieren oder Neuinstallieren mit vorhandenen Graphen
- Behoben: Parameter-Anzeige im Viewport nutzt die Einheit der Szene

## 0.1.0

Erste Version.

- Eigener Node-Graph „Parametric Tree“ mit Längen-, Winkel-, Zahl-, Vektor- und Geometrie-Sockets
- Grundkörper: Box, Zylinder, Kugel, Kegel
- Profile: Rechteck mit Eckradius, Kreis, Polygon, Polylinie; Extrudieren und Rotieren
- Operationen: Boolean, Bevel/Fase, Shell, Spiegeln, Zusammenfügen
- Modifier: Transform, Soften, lineares und radiales Array
- Parameter, Formeln (sicher ausgewertet), Objekt-Eingang, Gruppen mit exponierten Parametern
- Sync live / aufheben / Re-link / Bake, Fehler- und Dirty-Anzeige
- Duplizieren, Instanz, Gruppieren
- Toolbox mit großen Buttons, Radialmenü (Umschalt+Alt+Q), Parameter-Badges im Viewport
- Arbeitsbereich mit Viewport und Node-Editor, Node-Editor folgt dem aktiven Objekt
- 3D-Druck: Millimeter-Einheiten, Druck-Check, STL-Export
