#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · validate.py (Standard 3.1)

Prüft eine werk.json in vier Stufen:
  1. Struktur gegen schema.json
  2. Typografie und Zitierweise
  3. Codes, Verweise, Bausteinlogik, Rechnungen, Diagramme
  4. Formelsyntax (KaTeX über Node, falls verfügbar)

Aufruf:   python3 validate.py werk.json [--streng]
          --streng: Warnungen zählen als Fehler
Import:   from validate import validiere; bericht = validiere(werk)
Exitcode: 0 = keine Fehler, 1 = Fehler.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    sys.exit("jsonschema fehlt: pip install jsonschema --break-system-packages")

HIER = Path(__file__).resolve().parent
VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()

REIHENFOLGE = ["definition", "kern", "formel", "rechenweg", "schema", "beispiel",
               "merke", "feinheit", "klausurfalle", "austriacum", "aktualisierung",
               "latinum", "luecke"]
GERAHMT = {"merke", "feinheit", "klausurfalle", "austriacum", "aktualisierung", "latinum", "luecke"}
VARIANTEN = ["tabelle", "abgrenzung", "kurve", "tkonto", "zeitleiste", "fluss", "svg"]
MAX_GERAHMT, MAX_MARKER, MAX_TITEL = 4, 5, 60
UEBERHOEHE_ZEILEN = 30

STRICHE = {"\u2012": "Figure Dash", "\u2013": "Halbgeviertstrich", "\u2014": "Geviertstrich", "\u2015": "Horizontal Bar"}
ROH = (".tex", ".svg")  # Felder ohne Typografie- und Markup-Prüfung

RE_VERWEIS_ROH = re.compile(r"\[\[([^\]]*)\]\]")
RE_VERWEIS = re.compile(r"^(?:([A-Z]{2,5}):)?([A-GL][1-9][0-9]?)$")
RE_MARKER = re.compile(r"==(.+?)==")
RE_PARA_OHNE_LEER = re.compile(r"§§?(?=\d)")
RE_ABK_MIT_PUNKT = re.compile(r"\b(Art|Abs|lit)\.\s?\d")
RE_GERICHT = re.compile(r"\b(VwGH|VfGH|OGH|EuGH|EGMR)\b")
# Nur echte Rechtsprechungszitate prüfen, nicht die bloße Nennung eines Gerichts als Institution
RE_RSP_ZITAT = re.compile(r"\b(entschied|entschieden|judiziert|Erkenntnis|Urteil|Beschluss vom|Rechtssache|Rsp|stRsp|Judikatur|hat .{0,60}(anerkannt|festgehalten|ausgesprochen)|so auch)\b", re.I)
RE_GZ = re.compile(r"\b\d{2,4}/\d{2}/\d{4}\b"            # VwGH alt: 92/16/0015
                   r"|\b(?:Ro|Ra|Fe) \d{4}/\d{2}/\d{4}\b"  # VwGH neu: Ro 2017/08/0019
                   r"|\b\d{1,2} ?Ob[A-Za-z]* \d+/\d{2}[a-z]?\b"  # OGH: 1 Ob 23/20x
                   r"|\b[A-Z]{1,2} \d+/\d{4}\b"           # VfGH: G 258/2017
                   r"|\bVfSlg \d+|\bC-\d+/\d{2}\b|\b\d+/\d{2}\b")  # VfSlg, EuGH, EGMR
RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
RE_NAMENSFARBE = re.compile(r'(?:fill|stroke|color)\s*[=:]\s*"?(?!none|currentColor|var\()([a-z]+)', re.I)
ABKUERZUNGEN = ["z. B.", "d. h.", "u. a.", "o. Ä.", "bzw.", "vgl.", "Gl.", "Nr.", "S.", "Rz.", "ua.", "zB.", "idgF.", "iVm.", "hM.", "Rsp.", "p. a."]


class Bericht:
    def __init__(self):
        self.fehler, self.warnungen, self.hinweise = [], [], []

    def f(self, ort, msg):
        self.fehler.append(f"FEHLER   {ort}: {msg}")

    def w(self, ort, msg):
        self.warnungen.append(f"WARNUNG  {ort}: {msg}")

    def h(self, ort, msg):
        self.hinweise.append(f"HINWEIS  {ort}: {msg}")

    @property
    def ok(self):
        return not self.fehler


def alle_strings(obj, pfad="$"):
    if isinstance(obj, str):
        yield pfad, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from alle_strings(v, f"{pfad}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from alle_strings(v, f"{pfad}[{i}]")


def ist_roh(pfad):
    return pfad.endswith(ROH)


# 1 · Struktur ──────────────────────────────────────────────────────────────
def pruefe_struktur(werk, b):
    schema = json.loads((HIER / "schema.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)
    for err in sorted(v.iter_errors(werk), key=lambda e: list(e.absolute_path)):
        if err.validator in ("allOf", "if"):  # Folgefehler der Typweiche, Detail kommt separat
            continue
        ort = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        b.f(ort, err.message[:240])


# 2 · Typografie, Markup, Zitierweise ───────────────────────────────────────
def pruefe_typografie(werk, b):
    for pfad, s in alle_strings(werk):
        for zeichen, name in STRICHE.items():
            if zeichen in s:
                i = s.index(zeichen)
                b.f(pfad, f"{name} (Gedankenstrich verboten): …{s[max(0, i-30):i+30]}…")
        if ist_roh(pfad):
            continue
        if re.search(r"\s-\s|--", s):
            b.w(pfad, "Bindestrich als Gedankenstrich verwendet")
        if '"' in s:
            b.w(pfad, 'gerades Anführungszeichen ("), typografisch „…“ verwenden')
        if s.count("**") % 2:
            b.f(pfad, "unpaariges ** (Fettung nicht geschlossen)")
        if s.count("==") % 2:
            b.f(pfad, "unpaariges == (Textmarker nicht geschlossen)")
        if s.replace("**", "").count("*") % 2:
            b.f(pfad, "unpaariges * (Kursivierung nicht geschlossen)")
        if RE_PARA_OHNE_LEER.search(s):
            b.w(pfad, "§ ohne Leerzeichen vor der Zahl (Renderer setzt geschütztes Leerzeichen nur bei vorhandenem Abstand)")
        if RE_GERICHT.search(s) and RE_RSP_ZITAT.search(s) and not RE_GZ.search(s):
            b.w(pfad, "Rechtsprechung zitiert, aber keine Geschäftszahl gefunden")
        if RE_ABK_MIT_PUNKT.search(s):
            b.w(pfad, "Art./Abs./lit. mit Punkt; österreichische Zitierweise ohne Punkt (Art 7, Abs 1, lit a)")


# 3 · Codes und Verweise ────────────────────────────────────────────────────
def pruefe_codes_und_verweise(werk, b):
    provinzen = werk.get("provinzen", [])
    typ = werk.get("meta", {}).get("typ")
    codes = {}
    nicht_l = [p for p in provinzen if p.get("code") != "L"]
    for i, p in enumerate(nicht_l):
        soll = "ABCDEFG"[i] if i < 7 else "?"
        if p.get("code") != soll:
            b.f(f"Provinz {p.get('nr')}", f"Code {p.get('code')} statt {soll} (lückenlos ab A)")
    if not provinzen or provinzen[-1].get("code") != "L":
        b.f("Provinzen", "letzte Provinz muss Code L (Repetitorium) tragen")
    if sum(p.get("code") == "L" for p in provinzen) > 1:
        b.f("Provinzen", "Code L mehrfach vergeben")
    for i, p in enumerate(provinzen):
        soll = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"][i] if i < 8 else "?"
        if p.get("nr") != soll:
            b.f(f"Provinz {p.get('code')}", f"römische Nummer {p.get('nr')} statt {soll}")
    if typ == "werk" and not 5 <= len(provinzen) <= 8:
        b.w("Provinzen", f"{len(provinzen)} Provinzen; Standard sind 5 bis 8")

    for p in provinzen:
        kach = p.get("kacheln", [])
        if typ == "werk" and p.get("code") != "L" and not 4 <= len(kach) <= 9:
            b.w(f"Provinz {p.get('code')}", f"{len(kach)} Kacheln; Standard sind 4 bis 9")
        nummern = []
        for k in kach:
            c = k.get("code", "")
            if c[:1] != p.get("code"):
                b.f(c, f"Kachelcode passt nicht zu Provinz {p.get('code')}")
            if c in codes:
                b.f(c, "Kachelcode doppelt vergeben")
            codes[c] = k
            if c[1:].isdigit():
                nummern.append(int(c[1:]))
        if nummern and nummern != sorted(nummern):
            b.f(f"Provinz {p.get('code')}", "Kacheln nicht aufsteigend nach Code geordnet")

    sigle = werk.get("meta", {}).get("kurz")
    for pfad, s in alle_strings(werk):
        if ist_roh(pfad):
            continue
        for roh in RE_VERWEIS_ROH.findall(s):
            m = RE_VERWEIS.match(roh)
            if not m:
                b.f(pfad, f"Verweis [[{roh}]] fehlerhaft (Form [[D7]] oder [[ADM:D7]])")
                continue
            fremd, ziel = m.groups()
            if fremd and fremd != sigle:
                b.h(pfad, f"terraübergreifender Verweis {fremd}:{ziel}, Ziel extern")
            elif ziel not in codes:
                b.f(pfad, f"Verweis [[{ziel}]] zeigt auf keine Kachel")

    for feld in ("selbsttest", "quellenkritik", "lexicon"):
        for i, e in enumerate(werk.get(feld, [])):
            if e.get("kachel") not in codes:
                b.f(f"{feld}[{i}]", f"Kachel {e.get('kachel')} existiert nicht")
    return codes


# 3 · Kacheln und Bausteine ─────────────────────────────────────────────────
def pruefe_kacheln(werk, codes, b):
    domaene = werk.get("modul", {}).get("domaene")
    typ = werk.get("meta", {}).get("typ")
    for c, k in codes.items():
        bausteine = k.get("bausteine", [])
        typen = [x.get("typ") for x in bausteine]
        idx = [REIHENFOLGE.index(t) for t in typen if t in REIHENFOLGE]
        if idx != sorted(idx):
            b.f(c, f"Bausteinreihenfolge verletzt: {typen}")
        if typen and typen[0] not in ("definition", "kern") and not c.startswith("L"):
            b.w(c, f"Kachel beginnt mit „{typen[0]}“ statt mit Definition oder Kern")
        gerahmt = [t for t in typen if t in GERAHMT]
        if len(gerahmt) > MAX_GERAHMT:
            b.f(c, f"{len(gerahmt)} gerahmte Bausteine (max. {MAX_GERAHMT}); Kachel teilen")
        if domaene == "recht" and "austriacum" in typen:
            b.f(c, "Austriacum in der Rechtsdomäne unzulässig (Anker ist bereits Österreichbezug)")
        if len(k.get("titel", "")) > MAX_TITEL:
            b.w(c, f"Titel über {MAX_TITEL} Zeichen; bricht im Kachelkopf um")
        if typ == "werk":
            if not k.get("seite"):
                b.w(c, "keine Seiten- oder Folienangabe")
            if k.get("test"):
                b.w(c, "Feld „test“ ist dem Referenzwerk vorbehalten")
        if "luecke" in typen:
            b.h(c, "enthält Lücke (sinngemäß ergänzt); in Abschlussmeldung nennen")
        marker = sum(len(RE_MARKER.findall(s)) for p, s in alle_strings(bausteine) if not ist_roh(p))
        if marker:
            b.w(c, f"{marker} Textmarker ==…== ohne Wirkung (Textmarker seit Oktober 2026 entfernt); Syntax streichen")
        for x in bausteine:
            if x.get("typ") == "schema":
                pruefe_schema(c, x, b)

    relevanzen = [k.get("relevanz") for k in codes.values()]
    if typ == "werk" and relevanzen and relevanzen.count("kern") / len(relevanzen) > 0.75:
        b.w("Relevanz", f"{relevanzen.count('kern')} von {len(relevanzen)} Kacheln als Kernstoff markiert; Marke verliert Aussagekraft")

    lat = {}
    for c, k in codes.items():
        for x in k.get("bausteine", []):
            if x.get("typ") == "latinum":
                key = x.get("lat", "").strip().lower()
                if key in lat:
                    b.w(c, f"Latinum „{x.get('lat')}“ bereits in {lat[key]}")
                lat[key] = c


def pruefe_schema(c, x, b):
    v = x.get("variante")
    ort = f"{c} Schema „{x.get('titel')}“"
    if v == "tabelle":
        n = len(x.get("kopf", []))
        for i, z in enumerate(x.get("zeilen", [])):
            if len(z) != n:
                b.f(ort, f"Zeile {i+1} hat {len(z)} Zellen, Kopf hat {n}")
            if any(not str(zelle).strip() for zelle in z):
                b.w(ort, f"Zeile {i+1} enthält leere Zelle (für „nicht anwendbar“ ausdrücklich „entfällt“ schreiben)")
        if n > 5 and not x.get("breit"):
            b.w(ort, f"{n} Spalten ohne breit=true; im Skript droht Enge")
        if n > 9:
            b.f(ort, f"{n} Spalten; auch im Querformat nicht lesbar, Tabelle teilen")
    elif v == "kurve":
        for r in x.get("reihen", []):
            xs = [p[0] for p in r.get("punkte", [])]
            if xs != sorted(xs) or len(xs) != len(set(xs)):
                b.f(ort, f"Reihe „{r.get('name')}“: x-Werte nicht streng aufsteigend")
    elif v == "tkonto":
        soll = sum(e["betrag"] for k in x.get("konten", []) for e in k.get("soll", []))
        haben = sum(e["betrag"] for k in x.get("konten", []) for e in k.get("haben", []))
        if abs(soll - haben) > 0.005:
            b.f(ort, f"Soll {soll:,.2f} ≠ Haben {haben:,.2f}")
    elif v == "fluss":
        pruefe_fluss(ort, x, b)
    elif v == "svg":
        svg = x.get("svg", "")
        if "viewBox" not in svg:
            b.f(ort, "SVG ohne viewBox; skaliert nicht")
        if RE_HEX.search(svg) or RE_NAMENSFARBE.search(svg):
            b.f(ort, "SVG mit fester Farbe; nur Klassen t-flaeche, t-akzent, t-linie, t-text, t-klein verwenden (Dark Mode)")
        if re.search(r"<script|on[a-z]+=", svg, re.I):
            b.f(ort, "SVG enthält Skript oder Event-Handler")


def pruefe_fluss(ort, x, b):
    knoten = {k["id"]: k for k in x.get("knoten", [])}
    if len(knoten) != len(x.get("knoten", [])):
        b.f(ort, "doppelte Knoten-ID")
    pos = [(k["zeile"], k["spalte"]) for k in x.get("knoten", [])]
    if len(pos) != len(set(pos)):
        b.f(ort, "zwei Knoten auf derselben Rasterposition")
    starts = [k for k in knoten.values() if k["art"] == "start"]
    if len(starts) != 1:
        b.f(ort, f"{len(starts)} Startknoten (genau einer verlangt)")
    aus = {i: [] for i in knoten}
    for e in x.get("kanten", []):
        if e["von"] not in knoten or e["nach"] not in knoten:
            b.f(ort, f"Kante {e['von']} → {e['nach']}: unbekannter Knoten")
            continue
        aus[e["von"]].append(e)
        if knoten[e["nach"]]["zeile"] <= knoten[e["von"]]["zeile"]:
            b.f(ort, f"Kante {e['von']} → {e['nach']} führt nicht abwärts (Layout erlaubt nur Abwärtskanten)")
    for i, k in knoten.items():
        n = len(aus[i])
        if k["art"] in ("ergebnis", "sperre") and n:
            b.f(ort, f"Endknoten „{i}“ hat ausgehende Kanten")
        if k["art"] == "frage" and n < 2:
            b.f(ort, f"Frageknoten „{i}“ hat {n} Ausgang (mindestens zwei)")
        if k["art"] == "frage" and any(not e.get("label") for e in aus[i]):
            b.f(ort, f"Frageknoten „{i}“: Ausgang ohne Beschriftung (ja/nein)")
        if k["art"] in ("start", "station") and n < 1 and k["art"] == "start":
            b.f(ort, "Startknoten ohne Ausgang")
    if starts:
        gesehen, offen = set(), [starts[0]["id"]]
        while offen:
            i = offen.pop()
            if i not in gesehen:
                gesehen.add(i)
                offen += [e["nach"] for e in aus.get(i, [])]
        tot = set(knoten) - gesehen
        if tot:
            b.f(ort, f"vom Start nicht erreichbar: {sorted(tot)}")


def pruefe_provinzen(werk, b):
    for p in werk.get("provinzen", []):
        for i, satz in enumerate(p.get("kompakt", [])):
            rest = satz
            for a in ABKUERZUNGEN:
                rest = rest.replace(a, "")
            rest = re.sub(r"\b\d+\.(?=\s)", "", rest)  # Ordinalzahlen („19. Jahrhundert“) sind kein Satzende
            if len(re.findall(r"[.!?](?=\s+[A-ZÄÖÜ])", rest)) > 0:
                b.w(f"Provinz {p.get('code')} kompakt[{i}]", "mehrere Sätze in einem Eintrag; je Eintrag ein Satz")
    if werk.get("meta", {}).get("typ") == "werk":
        n = len(werk.get("selbsttest", []))
        if n < 5:
            b.w("Selbsttest", f"{n} Fragen; Standard sind 5 bis 10")
        if not werk.get("aenderungen"):
            b.w("Änderungsprotokoll", "leer; mindestens Erstfassung eintragen")
    prot = werk.get("aenderungen") or []
    if prot and prot[-1].get("version") != werk.get("meta", {}).get("version"):
        b.w("Änderungsprotokoll", f"letzter Eintrag gilt Version {prot[-1].get('version')}, Werk ist "
                                  f"{werk.get('meta', {}).get('version')}; Eintrag ergänzen (python3 diff.py alt.json neu.json --eintragen)")


# 4 · Formeln ───────────────────────────────────────────────────────────────
KATEX_JS = r"""
const k = require(process.argv[1]);
const fs = require('fs');
const liste = JSON.parse(fs.readFileSync(0, 'utf8'));
const aus = [];
for (const [ort, tex] of liste) {
  try { k.renderToString(tex, {throwOnError: true, displayMode: true}); }
  catch (e) { aus.push([ort, e.message.split('\n')[0].slice(0, 160)]); }
}
console.log(JSON.stringify(aus));
"""


def finde_katex():
    for kandidat in [HIER / "node_modules" / "katex", Path("/tmp/ktx/node_modules/katex")]:
        if (kandidat / "package.json").exists():
            return kandidat
    return None


def pruefe_formeln(werk, b):
    liste = [(p, s) for p, s in alle_strings(werk) if p.endswith(".tex")]
    if not liste:
        return
    katex = finde_katex()
    if not shutil.which("node") or not katex:
        b.w("Formeln", f"{len(liste)} Formeln ungeprüft (Node oder KaTeX fehlt; npm install katex)")
        return
    r = subprocess.run(["node", "-e", KATEX_JS, str(katex)], input=json.dumps(liste),
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        b.w("Formeln", f"KaTeX-Prüfung abgebrochen: {r.stderr[:160]}")
        return
    for ort, msg in json.loads(r.stdout):
        b.f(ort, f"Formel nicht setzbar: {msg}")


# Referenzwerk: Abdeckung ───────────────────────────────────────────────────
def pruefe_abdeckung(werk, codes, b):
    if werk.get("meta", {}).get("typ") != "referenz":
        return
    alle = [x for k in codes.values() for x in k.get("bausteine", [])]
    typen = {x.get("typ") for x in alle}
    varianten = {x.get("variante") for x in alle if x.get("typ") == "schema"}
    for t in REIHENFOLGE:
        if t not in typen:
            b.f("Abdeckung", f"Baustein „{t}“ fehlt im Referenzwerk")
    for v in VARIANTEN:
        if v not in varianten:
            b.f("Abdeckung", f"Schemavariante „{v}“ fehlt im Referenzwerk")
    tabellen = [x for x in alle if x.get("variante") == "tabelle"]
    if not any(x.get("breit") for x in tabellen):
        b.f("Abdeckung", "keine breite Tabelle (Querformattest)")
    if not any(len(x.get("zeilen", [])) >= UEBERHOEHE_ZEILEN for x in tabellen):
        b.f("Abdeckung", f"keine Tabelle mit mindestens {UEBERHOEHE_ZEILEN} Zeilen (Überhöhentest)")
    rel = {k.get("relevanz") for k in codes.values()}
    for r in ("kern", "vertiefung", "auslassbar"):
        if r not in rel:
            b.f("Abdeckung", f"Relevanz „{r}“ fehlt")
    texte = " ".join(s for _, s in alle_strings(werk))
    if not re.search(r"\[\[[A-Z]{2,5}:", texte):
        b.f("Abdeckung", "kein terraübergreifender Verweis")
    if not any(k.get("bausteine", [{}])[0].get("zitat") for k in codes.values()):
        b.f("Abdeckung", "kein Normwortlaut (zitat)")


# 3a · Quellen ──────────────────────────────────────────────────────────────
PFLICHT = {  # je Gattung: alle Felder der Liste; Tupel heißt „eines davon“
    "literatur": ["titel", "jahr", ("autoren", "hrsg", "institution")],
    "beitrag": ["autoren", "titel", "in", "jahr"],
    "kommentar": ["autoren", "hrsg", "in", "fundstelle", "jahr"],
    "aufsatz": ["autoren", "titel", "in", "jahr"],
    "lv": ["titel", "jahr", ("autoren", "institution")],
    "daten": ["titel", "jahr", "abruf", ("autoren", "institution")],
    "online": ["titel", "abruf", ("url", "institution")],
    "norm": ["abk", "titel", "fundstelle"],
    "entscheidung": ["gericht", "datum", "gz"],
    "materialien": ["titel", "fundstelle"],
}


def pruefe_quellen(werk, codes, b):
    quellen = werk.get("quellen", [])
    kurz = [q.get("kurz") for q in quellen]
    for k in sorted({x for x in kurz if kurz.count(x) > 1}):
        b.f("quellen", f"Kurzzitat „{k}“ doppelt vergeben")
    for i, q in enumerate(quellen):
        g = q.get("gattung")
        if not g:
            b.h(f"quellen[{i}]", f"„{q.get('kurz')}“ im alten Format (nur voll); bei der nächsten Überarbeitung strukturiert erfassen")
            continue
        for feld in PFLICHT.get(g, []):
            felder = feld if isinstance(feld, tuple) else (feld,)
            if not any(q.get(f) for f in felder):
                b.f(f"quellen[{i}]", f"„{q.get('kurz')}“ ({g}): Pflichtangabe {' oder '.join(felder)} fehlt")
    bekannt = set(kurz)
    benutzt = set()
    for c, k in codes.items():
        for z in k.get("quellen", []):
            if z not in bekannt:
                b.f(c, f"zitiert „{z}“, das im Quellenverzeichnis fehlt")
            benutzt.add(z)
    if benutzt:  # Verwendungsnachweis geführt: jede strukturierte Quelle muss verwendet sein
        for q in quellen:
            if q.get("gattung") and q["kurz"] not in benutzt:
                b.w("quellen", f"„{q['kurz']}“ wird von keiner Kachel zitiert")


def validiere(werk):
    b = Bericht()
    pruefe_struktur(werk, b)
    pruefe_typografie(werk, b)
    codes = pruefe_codes_und_verweise(werk, b)
    pruefe_kacheln(werk, codes, b)
    pruefe_quellen(werk, codes, b)
    pruefe_provinzen(werk, b)
    pruefe_formeln(werk, b)
    pruefe_abdeckung(werk, codes, b)
    b.codes = codes
    return b


# ── Exam ──────────────────────────────────────────────────────────────────
def validiere_exam(exam, werk):
    """Prüft ein Exam gegen schema_exam.json, die Regeln des Exam-Standards und das zugehörige Werk."""
    b = Bericht()
    schema = json.loads((HIER / "schema_exam.json").read_text(encoding="utf-8"))
    for err in sorted(jsonschema.Draft202012Validator(schema).iter_errors(exam), key=lambda e: list(e.absolute_path)):
        ort = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        b.f(ort, err.message[:240])
    if b.fehler:
        return b
    m, fragen = exam["meta"], exam["fragen"]
    if m["werk"] != werk["meta"]["titel"]:
        b.f("meta.werk", f"Exam gehört zu „{m['werk']}“, übergeben wurde „{werk['meta']['titel']}“")
    if m["werk_version"] != werk["meta"]["version"]:
        b.w("meta.werk_version", f"Exam für Version {m['werk_version']}, Werk ist {werk['meta']['version']}; Fragen gegen das Werk prüfen")
    codes = {k["code"]: p["code"] for p in werk["provinzen"] for k in p["kacheln"]}
    provinzen = [p["code"] for p in werk["provinzen"]]
    dims = werk["modul"]["pruefdimensionen"]
    n = len(fragen)
    if not 24 <= n <= 30:
        b.f("Fragen", f"{n} Fragen; verlangt sind 24 bis 30")
    ids = [f["id"] for f in fragen]
    if ids != [f"q{i}" for i in range(1, n + 1)]:
        b.f("Fragen", "IDs nicht fortlaufend q1, q2, …")
    for f in fragen:
        ort = f["id"]
        if [o["id"] for o in f["optionen"]] != ["a", "b", "c", "d"]:
            b.f(ort, "Optionen nicht in der Reihenfolge a, b, c, d")
        r = sum(o["richtig"] for o in f["optionen"])
        if f["typ"] == "einfach" and r != 1:
            b.f(ort, f"Einfachauswahl mit {r} richtigen Optionen (genau eine verlangt)")
        if f["typ"] == "mehrfach" and r == 0:
            b.f(ort, "Mehrfachauswahl ohne richtige Option")
        if f["typ"] == "mehrfach" and r == 4:
            b.w(ort, "alle vier Optionen richtig; als Prüfungsfrage schwach")
        if f["provinz"] not in provinzen:
            b.f(ort, f"Provinz {f['provinz']} existiert im Werk nicht")
        for k in f["kacheln"]:
            if k not in codes:
                b.f(ort, f"Kachel {k} existiert im Werk nicht")
        if f["kacheln"] and all(codes.get(k) != f["provinz"] for k in f["kacheln"]):
            b.w(ort, f"keine der Kacheln {f['kacheln']} liegt in Provinz {f['provinz']}")
        if f["dimension"] not in dims:
            b.f(ort, f"Prüfdimension „{f['dimension']}“ nicht im Domänenmodul ({', '.join(dims)})")
        if werk["modul"]["domaene"] in ("recht", "gemischt"):
            for o in f["optionen"]:
                if not o.get("norm"):
                    b.h(ort + o["id"], "Begründung ohne Normzitat")
    fall = sum(1 for f in fragen if f.get("sachverhalt"))
    if fall * 3 < n * 2:
        b.f("Fallquote", f"{fall} von {n} Fragen mit Sachverhalt; verlangt sind mindestens zwei Drittel")
    mehr = sum(1 for f in fragen if f["typ"] == "mehrfach")
    if not 0.35 <= mehr / max(n, 1) <= 0.65:
        b.w("Mischung", f"{mehr} von {n} Mehrfachauswahlfragen; Standard etwa die Hälfte")
    for p in provinzen:
        z = sum(1 for f in fragen if f["provinz"] == p)
        if p != "L" and z < 2:
            b.f("Abdeckung", f"Provinz {p} nur {z}-mal geprüft (mindestens zweimal)")
    for d in dims:
        z = sum(1 for f in fragen if f["dimension"] == d)
        if z < 3:
            b.f("Abdeckung", f"Prüfdimension „{d}“ nur {z}-mal (mindestens dreimal)")
    # Ausgewogenheit (3.3): keine Dimension mehr als doppelt so oft wie die seltenste
    zahl = {d: sum(1 for f in fragen if f["dimension"] == d) for d in dims}
    if zahl and min(zahl.values()) > 0 and max(zahl.values()) > 2 * min(zahl.values()):
        hoch, tief = max(zahl, key=zahl.get), min(zahl, key=zahl.get)
        b.w("Ausgewogenheit", f"Prüfdimension „{hoch}“ {zahl[hoch]}-mal, „{tief}“ nur {zahl[tief]}-mal "
                              "(höchstens das Doppelte der seltensten Dimension)")
    for pfad, s in alle_strings(exam):
        for zeichen, name in STRICHE.items():
            if zeichen in s:
                b.f(pfad, f"{name} (Gedankenstrich verboten)")
        if '"' in s:
            b.w(pfad, 'gerades Anführungszeichen ("), typografisch „…“ verwenden')
        if RE_ABK_MIT_PUNKT.search(s):
            b.w(pfad, "Art./Abs. mit Punkt; österreichische Zitierweise ohne Punkt")
    b.matrix = {p: {d: sum(1 for f in fragen if f["provinz"] == p and f["dimension"] == d) for d in dims} for p in provinzen}
    b.kennzahlen = {"fragen": n, "fallbeispiele": fall, "mehrfach": mehr}
    return b


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    streng = "--streng" in sys.argv
    if len(args) == 2:  # Exam: validate.py exam.json werk.json
        exam = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        werk = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        b = validiere_exam(exam, werk)
        print(f"Terra-Validator {VERSION} · {exam.get('meta', {}).get('titel')} zu {werk['meta']['titel']}")
        if hasattr(b, "kennzahlen"):
            k = b.kennzahlen
            print(f"{k['fragen']} Fragen, {k['fallbeispiele']} mit Sachverhalt, {k['mehrfach']} Mehrfachauswahl")
            dims = werk["modul"]["pruefdimensionen"]
            print("Prüfungsmatrix (Provinz × Dimension):")
            print("      " + " ".join(f"{d[:10]:>11}" for d in dims))
            for p, z in b.matrix.items():
                print(f"  {p}   " + " ".join(f"{z[d]:>11}" for d in dims))
        for z in b.fehler + b.warnungen:
            print(z)
        print(f"Ergebnis: {len(b.fehler)} Fehler, {len(b.warnungen)} Warnungen, {len(b.hinweise)} Hinweise")
        sys.exit(1 if b.fehler or (streng and b.warnungen) else 0)
    if len(args) != 1:
        sys.exit("Aufruf: python3 validate.py werk.json [--streng]  oder  validate.py exam.json werk.json")
    werk = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    b = validiere(werk)
    typen = sorted({x.get("typ") for k in b.codes.values() for x in k.get("bausteine", [])})
    print(f"Terra-Validator {VERSION} · {werk.get('meta', {}).get('titel')} · "
          f"{len(werk.get('provinzen', []))} Provinzen, {len(b.codes)} Kacheln")
    print(f"Bausteintypen: {', '.join(typen)}")
    for z in b.fehler + b.warnungen + b.hinweise:
        print(z)
    print(f"Ergebnis: {len(b.fehler)} Fehler, {len(b.warnungen)} Warnungen, {len(b.hinweise)} Hinweise")
    sys.exit(1 if b.fehler or (streng and b.warnungen) else 0)


if __name__ == "__main__":
    main()
