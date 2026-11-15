# Konzept: Maßvorschläge, Druckprüfung, Proportionssperre

Stand: 15.11.2026 · Entwurf zur Diskussion · baut auf [KONZEPT.md](KONZEPT.md) (Version 3, Plugin 0.2) auf

Dieses Dokument beschreibt drei neue Funktionen. Es ist ein Konzept, noch keine Umsetzung.
Zu jeder Funktion steht, was man sieht und tut, wie sie sich in Toolbox, Node-Graph,
Parameter und Skizzen-Solver einfügt, und was in Blender technisch machbar ist.

1. **Maßvorschläge:** Das Plugin zeigt Abstände, die sich als Parameter eignen würden, zum
   Beispiel den Abstand einer Bohrung vom Rand. Ein Tipp macht daraus einen Parameter.
2. **Druckprüfung und Stabilität:** Der vorhandene Druck-Check wird zu einer Ampel mit
   Druckprofil, Wandstärke, Überhängen, Standfestigkeit und Schwachstellen.
3. **Proportionssperre:** Verhältnisse innerhalb einer Form (Breite : Tiefe, Bohrung zur
   Wand, Deckel zur Dose) lassen sich sperren, damit sie beim Ändern erhalten bleiben.

Die drei greifen ineinander: Maßvorschläge erzeugen Parameter, die Proportionssperre hält
Parameter zueinander fest, und die Druckprüfung liefert Grenzen für Parameter. Deshalb
gibt es einen gemeinsamen Baustein, die **Parameterbereiche** (Abschnitt 4).

---

## 1. Maßvorschläge („Maße finden“)

### 1.1 Was man sieht und tut

- In der Toolbox, Kategorie **Parameter**, kommt die Kachel **Maße vorschlagen** dazu. Icon
  nach dem Zwei-Farben-Prinzip: Bauteil hellgrau, Maßlinie mit Pfeilen grün.
- Ist sie an, zeichnet der Viewport **gestrichelte, blasse Maßlinien** mit Wert, zum Beispiel
  `8 mm` zwischen Bohrung und linkem Rand. Es werden nur die besten Vorschläge gezeigt
  (Standard: 6, einstellbar), damit das Bild ruhig bleibt.
- **Tippen** (Stift oder Maus) auf eine Maßlinie öffnet ein kleines Popover:
  `Name: rand_links` · `Wert: 8 mm` · **[Als Parameter]** · [Nur messen] · [Ausblenden].
- Nach **Als Parameter** wird die Linie durchgezogen und grün, mit Namen am Badge, so wie die
  bestehenden Maß-Badges `l`, `b`, `h` im Mockup. Ab jetzt steuert das Maß die Geometrie:
  Wird das Teil breiter, bleibt die Bohrung 8 mm vom Rand.
- **Ziehen** an einer grünen Maßlinie ändert den Wert direkt. Der Wert rastet auf ganze mm,
  mit Umschalt auf 0,1 mm. Mit dem Stift gilt dieselbe Druck-Logik wie beim Snap:
  leichter Druck frei, fester Druck rastet.
- **Halten** auf einer Maßlinie öffnet das Umbenennen; **Doppeltippen** öffnet die Wert-Eingabe.

### 1.2 Welche Abstände vorgeschlagen werden

Das Plugin kennt die Struktur des Modells aus dem Graph, nicht nur das fertige Mesh. Daraus
ergeben sich **Merkmale**: alles, was über einen Boolean-Eingang B, einen Join oder ein Array
zum Grundkörper kommt (Bohrung, Tasche, Zapfen, Rippe). Für jedes Merkmal werden Kandidaten
gebildet:

| Art | Beispiel |
|---|---|
| Randabstand | Kante der Bohrung bis Außenkante des Körpers |
| Achsabstand | Mittelpunkt der Bohrung bis Außenkante |
| Mittenabstand | zwischen zwei Bohrungen |
| Restwand | Boden unter einer Tasche, Wand neben einer Nut |
| Lücke im Array | Abstand zwischen zwei Elementen (statt Versatz von Mitte zu Mitte) |
| Überstand | Zapfen ragt 5 mm aus der Fläche |

In der **Skizze** (0.2) kommen Kandidaten direkt aus dem Solver: Abstände von Punkten zu
Achsen, zum Ursprung und zu anderen Linien.

**Rangfolge**, damit sinnvolle Vorschläge oben stehen:
1. In der Skizze: Maße, die einen offenen Freiheitsgrad schließen. Der Solver prüft das über
   den Rang der Jacobi-Matrix. So führen die Vorschläge zu einer voll bestimmten Skizze.
2. Achsparallele Abstände zwischen parallelen Flächen vor schrägen.
3. Kleine, runde Werte (8 mm vor 13,27 mm) und Abstände zur nächstgelegenen Kante.
4. **Symmetrie wird erkannt:** Sind links und rechts gleich, schlägt das Plugin statt zweier
   Maße **„Zentriert“** vor (eine Formel `x = 0` bzw. ein Mittelpunkt-Constraint in der Skizze).
5. Maße, die schon aus Parametern folgen, werden nicht als neu vorgeschlagen, sondern als
   *abgeleitet* grau mit Formel angezeigt.

### 1.3 Wie aus einem Maß ein Parameter wird

Das ist der technische Kern. Ein Maß wird am Ergebnis gemessen, ein Parameter muss aber einen
Eingang im Graph steuern.

**In der Skizze ist es einfach:** Das Maß wird ein `DISTANCE`-Constraint mit `expression =
rand_links`, dazu ein neuer Parameter-Node. Der Solver erledigt den Rest. Das funktioniert mit
dem Datenmodell aus 0.2 ohne Änderung am Solver.

**Am Körper** wird das Maß aus bekannten Größen zusammengesetzt. Beispiel Bohrung in Box:

```
Außenkante links   = box_mitte_x − breite / 2
Kante der Bohrung  = verschieben_x − radius
rand_links         = Kante der Bohrung − Außenkante
```

Daraus wird nach dem steuernden Eingang aufgelöst, und das Plugin legt automatisch an:

```
[Parameter Länge  rand_links = 8]──┐
[Parameter Länge  breite]──────────┼──▶ [Formel  −breite/2 + rand_links + radius] ──▶ Transform.Verschieben x
[Zylinder.Radius]──────────────────┘
```

Die Formel bezieht sich auf `breite`, also bleibt der Randabstand erhalten, wenn die Breite
sich ändert. Der Formel-Node wird als *aus Maß erzeugt* markiert, damit der Viewport die
Maßlinie weiter zeichnet und das Löschen des Maßes die Formel wieder entfernt.

Dafür merkt sich jeder Kandidat seine **Herkunft**: welcher Node die Fläche erzeugt hat,
welcher Eingang die Lage steuert, und wie (Vorzeichen, ± halbe Breite, ± Radius). Das geht
für die direkten Fälle: Grundkörper und Profile mit Transform davor, Arrays, Spiegeln.

**Grenze:** Hinter mehreren Booleans, Bevel oder Smooth lässt sich die Herkunft oft nicht mehr
eindeutig zurückverfolgen. Dann bietet das Plugin nur **Nur messen** an.

### 1.4 Neuer Node: Messen

**Nur messen** legt einen Node **Messen** an. Er hat keinen Geometrie-Ausgang, sondern einen
Längen-Ausgang mit dem gemessenen Wert. Der lässt sich in Formeln verwenden und in der
Druckprüfung als Bedingung (`rand_links ≥ 2 mm`, siehe 2.6). Der Messen-Node speichert seine
beiden Bezugselemente (Node + Merkmal + Seite), nicht Vertex-Nummern, damit er Änderungen der
Topologie übersteht.

### 1.5 Technik in Blender

- **Zeichnen:** wie das bestehende Overlay (`gpu` + `blf`), Maßlinien in Bildschirm-Koordinaten.
- **Tippen auf Linien:** eigenes modales Werkzeug wie das Skizzen-Werkzeug aus 0.2, mit
  Trefferprüfung im 2D-Abstand zur Linie (Trefferzone 12 px × UI-Skalierung, stiftgerecht).
- **Merkmale:** Der Evaluator hat pro Node das Zwischenergebnis (`memo`). Für Merkmale reicht
  die Bounding Box bzw. Achse und Radius des Zwischenergebnisses, umgerechnet in Weltkoordinaten.
  Kein Raycast nötig.
- **Kosten:** Kandidaten werden nach jeder Auswertung im selben Timer berechnet; das sind
  wenige Dutzend Vergleiche von Boxen und liegt deutlich unter einer Millisekunde.

---

## 2. Druckbarkeit und Stabilität

### 2.1 Ausgangslage

Der Druck-Check in 0.1 prüft Maße, Volumen, offene Kanten, lose Punkte und Teile und gibt
„Druckbereit“ oder „Nicht wasserdicht“ aus. Darauf baut das Konzept auf: gleiche Stelle im
Panel, gleicher Operator, aber eine Liste von Prüfungen mit Ampel und Anzeige im Viewport.

### 2.2 Druckprofil

Neue Einstellung in der Szene, im Panel **Druck** oben als Auswahl:

| Wert | Vorgabe FDM | Vorgabe Harz (SLA) |
|---|---|---|
| Düse / Auflösung | 0,4 mm | 0,05 mm |
| Schichthöhe | 0,2 mm | 0,05 mm |
| Mindestwand | 0,8 mm (2 Bahnen) | 0,5 mm |
| Kleinstes Detail | 0,4 mm | 0,2 mm |
| Max. Überhang | 45° | 30° (gegen Saugkräfte) |
| Max. Brücke | 10 mm | – |
| Passungsspiel | 0,2 mm | 0,1 mm |
| Bauraum | 220 × 220 × 250 mm | 145 × 80 × 165 mm |
| Material | PLA, PETG, ABS, TPU … | Standard-Harz, zäh … |

Profile lassen sich speichern (Add-on-Einstellungen), damit Jo seine Drucker einmal anlegt.

### 2.3 Prüfungen

Jede Prüfung liefert Grün / Gelb / Rot, eine Zahl und auf Wunsch eine Einfärbung im Viewport.

**Druckbarkeit**

| Prüfung | Was | Wie in Blender |
|---|---|---|
| Wasserdicht | offene Kanten, lose Punkte (vorhanden) | `bmesh`, wie bisher |
| Normalen | nach innen zeigende Flächen | Vorzeichen des Volumens je Teil |
| Selbstdurchdringung | Flächen schneiden sich | `mathutils.bvhtree.BVHTree.overlap` gegen sich selbst |
| Bauraum | passt das Teil in Druckrichtung | Bounding Box nach Druckausrichtung (2.5) |
| Wandstärke | Stellen dünner als Mindestwand | pro Fläche ein Strahl nach innen (`BVHTree.ray_cast` entlang −Normale), Abstand zur Gegenseite |
| Kleine Details | Stifte, Stege, Löcher unter dem kleinsten Detail | wie Wandstärke, zusätzlich Lochdurchmesser aus Merkmalen (1.2) |
| Überhang | Flächen, die nach unten zeigen und steiler als der Grenzwinkel sind | Normale: problematisch, wenn −n·z > sin(max. Überhang); Flächen auf dem Druckbett ausgenommen |
| Brücken | waagrechte Unterseiten, die länger als die max. Brücke sind | zusammenhängende Unterseiten-Regionen, kürzere Ausdehnung der Region |
| Spalt | Teile, die näher als das Passungsspiel beieinander liegen und verschmelzen würden | Abstand zwischen Inseln per BVH |
| Haftung | Auflagefläche auf dem Druckbett im Verhältnis zur Höhe | Fläche der Flächen bei z ≈ min |

**Stabilität**

| Prüfung | Was | Wie |
|---|---|---|
| Standfestigkeit | Kippt das fertige Teil? | Schwerpunkt aus dem Mesh (Summe der Tetraeder-Volumen × Mittelpunkt), Auflage-Polygon über `mathutils.geometry.convex_hull_2d`. Ergebnis: **Kippwinkel** (wie weit man es neigen kann, bis es kippt). Im Viewport: Schwerpunkt-Punkt und Auflage-Polygon |
| Kippen beim Druck | Hohe, schlanke Teile wackeln auf dem Druckbett | Höhe zu kleinster Breite der Auflage, ab ca. 3 : 1 gelb, ab 6 : 1 rot (Werte einstellbar) |
| Schwachstelle in Z | Bei FDM hält das Teil zwischen den Schichten am schlechtesten | Schnitte parallel zum Druckbett in 50–200 Höhen (`bmesh.ops.bisect_plane` auf einer Kopie), Fläche je Schnitt. Kurve „Querschnitt über Höhe“ im Panel, die schmalste Stelle wird im Viewport als Ring markiert |
| Hebel (Abschätzung, später) | Bricht ein Zapfen unter Last? | Man zieht mit dem Stift einen Kraftpfeil an eine Fläche. Das Plugin rechnet an der schwächsten Stelle mit der Balkenformel σ = M / W, W aus dem Schnitt, und vergleicht mit der Materialfestigkeit, in Z mit Abschlag (z. B. 50 %) |

Die Lastabschätzung ist ausdrücklich **keine FEM-Simulation** und wird im Panel auch so
beschriftet. Sie soll zeigen, welche Stelle zuerst bricht und ob man um Faktor 2 oder 20
daneben liegt.

### 2.4 Was man sieht und tut

- Panel **Druck** im Reiter *Parametric*: Profil-Auswahl, darunter die Ampel-Liste. Jede Zeile
  ist eine große Kachel-Zeile (44 px) mit Icon, Ergebnis und Zahl, zum Beispiel
  `● Wandstärke · 0,6 mm an 3 Stellen`.
- **Tippen auf eine Zeile** färbt die betroffenen Stellen im Viewport ein (Rot für Fehler,
  Gelb für Warnung) und springt mit der Ansicht dorthin. Erneutes Tippen blendet aus.
- In der Statuszeile unten links (Overlay) erscheint `Druck: 2 Warnungen`. Tippen darauf öffnet
  das Panel.
- **Live prüfen** (Schalter): Schnelle Prüfungen (wasserdicht, Bauraum, Überhang, Standfestigkeit)
  laufen nach jeder Neuberechnung mit. Teure (Wandstärke, Querschnitte, Spalt) laufen nur,
  wenn man auf **Gründlich prüfen** tippt oder 2 Sekunden nichts geändert wurde.
- Neues Icon **Druck prüfen** (Bauteil grau, überhängende Fläche grün) in der Toolbox und als
  Option im Radialmenü.

### 2.5 Druckausrichtung

Viele Probleme hängen davon ab, wie das Teil auf dem Druckbett liegt. Deshalb bekommt der
**Output-Node** eine Einstellung *Druckausrichtung*. Sie ändert nicht das Modell, sondern nur
Prüfung und STL-/3MF-Export.

**Ausrichtung vorschlagen** probiert die sechs Achsrichtungen und die größten ebenen Flächen
als Auflage, bewertet Überhangfläche, Höhe, Auflagefläche und Schwachstelle in Z und zeigt die
drei besten als kleine Vorschaubilder. Tippen übernimmt die Ausrichtung.

### 2.6 Verbindung zu Graph und Parametern

Hier liegt der Mehrwert gegenüber Blenders eigener 3D-Print-Toolbox: Das Plugin weiß, **welcher
Parameter** ein Problem verursacht.

- **Herkunft der Flächen:** Jeder Node schreibt beim Erzeugen eine Ganzzahl-Eigenschaft
  `param_origin` in die Flächen (bmesh-Layer). So sieht man: Die zu dünne Wand stammt aus dem
  Shell-Node, gesteuert von `wand = 0,6`. *Zu prüfen:* ob Blenders Boolean-Modifier (Exact) diese
  Flächen-Eigenschaft durchreicht; laut Blender-Doku werden generische Attribute übernommen, das
  muss am echten Modell getestet werden.
- **Vorschlag zur Behebung:** In der Ampel-Zeile steht dann `wand: 0,6 → 0,8 mm` mit einem Knopf
  **Anwenden**. Gerechnet wird über die Empfindlichkeit: Parameter leicht verändern, neu messen,
  linear hochrechnen, nochmal prüfen.
- **Bedingung-Node:** Ein Node mit einem Ausdruck, z. B. `rand_links >= 2` oder
  `wand >= druck.mindestwand`. Ist die Bedingung verletzt, zeigt der Node eine Warnung im Graph
  und die Ampel eine Zeile. `druck.*` gibt Zugriff auf die Werte des Druckprofils.
- **Parameterbereiche:** Aus dem Druckprofil ergeben sich Untergrenzen für Parameter
  (siehe Abschnitt 4). Ein Wandstärke-Parameter kann dann gar nicht unter 0,8 mm gezogen werden,
  oder er wird beim Ziehen rot.

### 2.7 Technik und Leistung

- Alles läuft mit `bmesh`, `mathutils.bvhtree` und `numpy`, ohne externe Pakete.
- Python in Blender darf `bpy`-Daten nicht aus einem Hintergrund-Thread lesen. Teure Prüfungen
  werden deshalb in Häppchen per `bpy.app.timers` abgearbeitet (z. B. 20 Schnitte pro Takt),
  damit die Oberfläche flüssig bleibt. Die reinen Rechnungen (Strahlen, Flächen) laufen auf
  Kopien der Daten mit `numpy` und können später in einen Thread wandern.
- Richtwerte: Für ein Druckteil mit 20 000 Flächen dauert die Wandstärke-Prüfung mit BVH etwa
  0,2 bis 0,5 s, 100 Querschnitte etwa 0,5 bis 1 s. Das ist Schätzung und wird im Prototyp gemessen.
- Einfärben im Viewport: ein `gpu`-Batch über das ausgewertete Mesh mit Farbe pro Fläche, nur
  so lange eine Ampel-Zeile ausgewählt ist.

---

## 3. Proportionssperre

### 3.1 Was gesperrt werden kann

| Sperre | Bedeutung | Beispiel |
|---|---|---|
| **Verhältnis** | Mitglieder ändern sich gemeinsam im festen Verhältnis | Breite : Tiefe : Höhe = 2 : 1 : 1 |
| **Differenz** | fester Abstand zwischen zwei Maßen | Deckel-Innenmaß = Dose-Außenmaß + 0,2 mm Spiel |
| **Wert fest** | Maß darf sich gar nicht ändern | Bohrung für M3-Schraube bleibt 3,2 mm |
| **Form** (Skizze) | Die ganze Skizze oder Auswahl darf nur gleichmäßig skaliert werden | Logo-Umriss behält seine Form |

Die Differenz-Sperre ist für den Druck besonders nützlich, weil Passungen fast immer so
funktionieren.

### 3.2 Was man sieht und tut

- **Im Panel:** Neben jedem Parameter steht ein kleines Schloss. Tippen auf das Schloss
  sperrt den Wert (Wert fest), das Feld wird ausgegraut.
- **Mehrere Maße verbinden:** Im Viewport nacheinander auf die Maß-Badges tippen (Stift) oder
  im Panel mehrere Parameter anhaken, dann **Proportion sperren** wählen (Kachel in der
  Kategorie Constraints, Icon: graues Rechteck, grüne Kette zwischen zwei Seiten). Ein kleines
  Menü fragt: Verhältnis · Differenz.
- **Anzeige:** Gesperrte Maße bekommen im Viewport und im Panel ein Kettensymbol und dieselbe
  Gruppenfarbe. In der Skizze steht am Maß `2 : 1` bzw. `+0,2`.
- **Ändern:** Man ändert **irgendein** Mitglied, die anderen ziehen mit. Das ist wichtig, damit
  man nicht erst nachsehen muss, welches Maß „führt“. Ausnahme: Ein Mitglied, das von einer
  Formel berechnet wird, kann man nicht direkt ändern; es wird dann automatisch zum führenden
  Mitglied der Gruppe.
- **Verhältnis neu festlegen:** Mit gedrückter Alt-Taste (oder Stift-Seitentaste) ein Maß ändern
  ändert nur dieses eine und speichert das neue Verhältnis. Alternativ: Schloss lösen, ändern,
  wieder sperren.
- **Ganzes Objekt:** Im Transform-Node bekommt *Skalieren* ein Kettenschloss für gleichmäßiges
  Skalieren, wie man es aus Blender beim Bildgrößen-Dialog kennt.

### 3.3 Umsetzung im Graph

Es gibt zwei Wege. Das Konzept schlägt eine Kombination vor.

**a) Parameter-Gruppe (Standard, beidseitig).** Eine Proportionsgruppe ist eine kleine Liste am
Node-Tree: Mitglieder (Parameter-Nodes), Art (Verhältnis/Differenz) und die beim Sperren
gemerkten Faktoren. Ändert man ein Mitglied, setzt ein Update-Callback die anderen:

```
Verhältnis:  neu_j = neu_i × faktor_j / faktor_i
Differenz:   neu_j = neu_i + (versatz_j − versatz_i)
```

Die Werte bleiben normale Zahlen, der Evaluator muss nichts davon wissen. Das ist schnell
umzusetzen. Ein Schutz gegen Rekursion ist nötig (die Mitglieder lösen beim Setzen wieder
ihr Update aus), ähnlich dem `state["evaluating"]`-Zähler im Evaluator.

**b) Formel (einseitig).** Für den Fall „B folgt immer A“ legt das Plugin eine Formel an,
`tiefe = breite × 0,5`. Das ist die Variante, wenn ein Mitglied von einer Formel kommt.

**Eingänge ohne Parameter:** Viele Werte sind nur Zahlen direkt am Node (z. B. der Radius am
Zylinder-Node). Sperrt man so einen Wert, macht das Plugin daraus mit einem Tipp einen
Parameter (wie beim Maßvorschlag) und nimmt ihn in die Gruppe auf.

**Regeln:**
- Ein Parameter gehört zu höchstens einer Proportionsgruppe. Sperrt man ihn in eine zweite,
  fragt das Plugin, ob die Gruppen zusammengelegt werden sollen.
- Gruppen in Untergraphen (Group-Node) funktionieren weiter. Exponierte Parameter zeigen die
  Kette auch am Group-Node.
- Stößt ein Mitglied an seinen Parameterbereich (Abschnitt 4), bleibt die ganze Gruppe stehen,
  und die Grenze wird angezeigt (z. B. „tiefe wäre 0,6 mm, Mindestwand 0,8 mm“).

### 3.4 Umsetzung in der Skizze

In der Skizze laufen Sperren über den Solver aus 0.2. Neue Constraint-Arten:

| Constraint | Residuum (null, wenn erfüllt) |
|---|---|
| `RATIO` (Längen) | `|L1| − k · |L2|` |
| `DIFFERENCE` (Längen) | `|L1| − |L2| − d` |
| `FORM` (Auswahl) | jeder Punkt `p_i − (c + s · R(φ) · (q_i − c₀))`, mit `q_i` = Lage beim Sperren, `c`, `s`, `φ` als zusätzliche Unbekannte |

`FORM` hält die Form starr und lässt nur Verschieben, Drehen und gleichmäßiges Skalieren zu.
`s` kann man wiederum an einen Parameter binden (z. B. `logo_breite`). Die Freiheitsgrad-Anzeige
des Solvers zählt diese Unbekannten mit. Alle drei passen in die vorhandene
Levenberg-Marquardt-Schleife, weil sie nur neue Residuen und Spalten sind.

---

## 4. Gemeinsamer Baustein: Parameterbereiche

Jeder Parameter-Node bekommt optional **Minimum** und **Maximum** (weiche Grenzen). Quellen:

- vom Nutzer eingetragen,
- aus dem Druckprofil (Mindestwand, kleinstes Detail, Bauraum),
- aus Bedingung-Nodes.

Beim Ziehen eines Wertes wird das Feld an der Grenze rot, und der Wert bleibt stehen. Mit
Umschalt lässt er sich bewusst darüber hinaus ziehen. Maßvorschläge (1), Proportionssperre (3)
und Druckprüfung (2) lesen und schreiben alle diese Grenzen. Das ist der erste Baustein, der
gebaut werden sollte.

---

## 5. Stift-Bedienung im Überblick

| Geste | Maßlinie | Ampel-Zeile | Maß-Badge |
|---|---|---|---|
| Tippen | Popover „Als Parameter“ | Stellen einfärben | auswählen (für Proportion sperren) |
| Doppeltippen | Wert eingeben | Ansicht auf die Stelle | Wert eingeben |
| Halten | Umbenennen | Erklärung und Behebungsvorschlag | Sperr-Menü |
| Ziehen | Wert ändern, Druck steuert Raster | – | Wert ändern, Gruppe zieht mit |
| Seitentaste beim Ziehen | – | – | Verhältnis neu festlegen |

Alle Trefferzonen sind mindestens 44 px groß bzw. 12 px um Linien, mit UI-Skalierung
multipliziert. Die Gesten laufen in einem gemeinsamen modalen Werkzeug **Maße**, damit sie
sich nicht mit Blenders eigener Auswahl im Viewport streiten.

## 6. Neue Teile im Überblick

| Bereich | Neu |
|---|---|
| Toolbox | Kacheln *Maße vorschlagen*, *Proportion sperren*, *Druck prüfen* |
| Nodes | *Messen*, *Bedingung*; Formel-Node mit Markierung „aus Maß erzeugt“ |
| Parameter-Node | Minimum/Maximum, Schloss (Wert fest), Gruppenzugehörigkeit |
| Output-Node | Druckausrichtung |
| Skizze/Solver | Constraints `RATIO`, `DIFFERENCE`, `FORM`; Vorschläge über Freiheitsgrade |
| Szene | Druckprofil, Liste der Proportionsgruppen am Tree |
| Panel | *Druck* mit Ampel, Querschnitt-Kurve, Ausrichtung |
| Overlay | Maßlinien, Ketten, Schwerpunkt, Auflage-Polygon, Einfärbung |

## 7. Vorschlag für die Reihenfolge

- **0.3** (passt zur bisherigen Roadmap, die Überhang und Wandstärke schon nennt):
  Parameterbereiche · Druckprofil · Ampel mit Wandstärke, Überhang, Bauraum, Standfestigkeit ·
  Proportionssperre für Parameter (Verhältnis, Differenz, Wert fest) · Maßvorschläge in der Skizze.
- **0.4:** Maßvorschläge am Körper mit Herkunft · Messen- und Bedingung-Node · Schwachstelle in Z ·
  Druckausrichtung vorschlagen · `FORM`-Constraint in der Skizze · Behebungsvorschläge.
- **Später:** Lastabschätzung mit Kraftpfeil · Brücken- und Spalt-Prüfung · Verschiebung von
  Prüfungen in einen Thread.

## 8. Offene Fragen an Jo

1. Soll **Proportion sperren** standardmäßig beidseitig sein (jedes Mitglied führt), wie hier
   vorgeschlagen, oder lieber mit einem festen führenden Maß?
2. Welche Drucker und Materialien sollen als Profil-Vorgaben mitkommen?
3. Ist die Lastabschätzung (Kraftpfeil) interessant genug für eine spätere Version, oder reicht
   die Schwachstellen-Anzeige?
