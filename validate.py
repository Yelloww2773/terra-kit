#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · validate.py (Standard 4.0)

Prüft eine werk.json in fünf Stufen:
  1. Struktur gegen schema.json (Standard 4.0; Werke 3.x vorher mit umsetzen.py umsetzen)
  2. Typografie und Zitierweise (alle Textfelder)
  3. Kapitel, Codes, Verweise, Bausteine (Tabellen, Kurven, T-Konten, Bäume, Bilder, SVG, Rechenproben), Quellen
  4. Satzregeln des Buchsatzes (skript.regeln: Einbettungen, Kernsätze, Randbelege, Normzitate, Kontrollfragen)
  5. Formelsyntax (KaTeX über Node)
Beim Referenzwerk (meta.typ „referenz“) zusätzlich die Abdeckung aller Bausteine und Varianten.

Aufruf:   python3 validate.py werk.json [--streng]          Werk
          python3 validate.py exam.json werk.json [--streng] Exam gegen sein Werk
          --streng: Warnungen zählen als Fehler
Import:   from validate import validiere; bericht = validiere(werk, ordner)
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
sys.path.insert(0, str(HIER))
VERSION = (HIER / "VERSION").read_text(encoding="utf-8").strip()
STANDARD = "4.0"

BLOCKTYPEN = ["absatz", "kernsatz", "spitzmarke", "aufzaehlung", "tabelle", "abbildung", "fallbeispiel", "merkband", "zitat",
              "steckbrief", "glossar", "akteure", "latinum", "definition", "kern", "formel", "rechenweg"]
VARIANTEN = ["zeitstrahl", "zeitleiste", "diagramm", "baum", "kurve", "tkonto", "svg", "bild"]
SPITZMARKEN = ["klausurhinweis", "austriacum", "aktualisierung", "luecke", "merke", "feinheit"]
ABBILDUNG = {"kurve", "fluss", "svg", "baum", "bild", "diagramm", "zeitstrahl", "zeitleiste", "tkonto"}  # Abbildungsverzeichnis
MAX_TITEL = 70
LANGE_TABELLE = 14  # wie skript.LANGE_TABELLE: ab hier darf eine Tabelle über die Seite laufen
ROEMISCH = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]

STRICHE = {"‒": "Figure Dash", "–": "Halbgeviertstrich", "—": "Geviertstrich", "―": "Horizontal Bar"}
ROH = (".tex", ".svg", ".ausdruck", ".daten")  # Felder ohne Typografie- und Markup-Prüfung

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
        self.codes = {}

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


def abschnitte(werk):
    """Alle Abschnitte in Lesefolge, mit Kapitelcode: Kapitel A bis G, danach die Abschnitte des Repetitoriums (L1 …)."""
    for k in werk.get("kapitel", []):
        for a in k.get("abschnitte", []):
            yield k.get("code"), a
    for a in (werk.get("repetitorium") or {}).get("abschnitte", []):
        yield "L", a


def bloecke(werk):
    """(Ort, Block) aller Bausteine: Einleitung, Abschnitte, Abschluss, Repetitorium."""
    for k in werk.get("kapitel", []):
        for i, x in enumerate(k.get("einleitung", [])):
            if isinstance(x, dict):
                yield f'{k["code"]} Einleitung {i + 1}', x
        for a in k.get("abschnitte", []):
            for i, x in enumerate(a.get("bloecke", [])):
                yield f'{a["code"]} Block {i + 1}', x
        for i, x in enumerate(k.get("abschluss", [])):
            yield f'{k["code"]} Abschluss {i + 1}', x
    for a in (werk.get("repetitorium") or {}).get("abschnitte", []):
        for i, x in enumerate(a.get("bloecke", [])):
            yield f'{a["code"]} Block {i + 1}', x


# 1 · Struktur ──────────────────────────────────────────────────────────────
def pruefe_struktur(werk, b):
    std = str(werk.get("standard", ""))
    if std != STANDARD:
        b.f("standard", f"Standard „{std}“; das Kit {VERSION} setzt Werke des Standards {STANDARD}"
                        + (" (Werk 3.x umsetzen: python3 umsetzen.py alt.json neu.json --liste nacharbeit.md)" if std.startswith("3") else ""))
        return
    for k in werk.get("kapitel", []):
        for a in k.get("abschnitte", []):
            if "relevanz" in a:
                b.f(a.get("code", "?"), "„relevanz“ gibt es im Standard 4.0 nicht; Kerninhalte mit „wichtig“: true kennzeichnen")
    schema = json.loads((HIER / "schema.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)
    for err in sorted(v.iter_errors(werk), key=lambda e: list(e.absolute_path)):
        if err.validator in ("allOf", "if"):  # Folgefehler der Typweiche, Detail kommt separat
            continue
        ort = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        if err.validator == "oneOf" and isinstance(err.instance, dict) and err.instance.get("variante") == "bild":
            b.f(ort, "Bild: genau eines der Felder „datei“ (verknüpft) oder „daten“ (eingebettet) angeben")
            continue
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
            b.f(pfad, "Bindestrich als Gedankenstrich verwendet")
        if '"' in s:
            b.f(pfad, 'gerades Anführungszeichen ("), typografisch „…“ verwenden')
        if s.count("**") % 2:
            b.f(pfad, "unpaariges ** (Fettung nicht geschlossen)")
        if s.replace("**", "").count("*") % 2:
            b.f(pfad, "unpaariges * (Kursivierung nicht geschlossen)")
        if RE_MARKER.search(s):
            b.w(pfad, "Textmarker ==…== ohne Wirkung (seit Oktober 2026 entfernt); Syntax streichen")
        if RE_PARA_OHNE_LEER.search(s):
            b.w(pfad, "§ ohne Leerzeichen vor der Zahl (Renderer setzt geschütztes Leerzeichen nur bei vorhandenem Abstand)")
        if RE_GERICHT.search(s) and RE_RSP_ZITAT.search(s) and not RE_GZ.search(s):
            b.w(pfad, "Rechtsprechung zitiert, aber keine Geschäftszahl gefunden")
        if RE_ABK_MIT_PUNKT.search(s):
            b.w(pfad, "Art./Abs./lit. mit Punkt; österreichische Zitierweise ohne Punkt (Art 7, Abs 1, lit a)")


# 3 · Kapitel, Codes und Verweise ───────────────────────────────────────────
def pruefe_kapitel(werk, b):
    typ = werk.get("meta", {}).get("typ", "werk")
    probe = bool(werk.get("meta", {}).get("probesatz"))  # Probesatz: Auszug eines Werks, Codes und Nummern aus meta.provinzen
    register = {p["code"]: p["nr"] for p in werk.get("meta", {}).get("provinzen", [])}
    if probe:
        typ = "probe"
    kapitel = werk.get("kapitel", [])
    for i, k in enumerate(kapitel):
        soll = "ABCDEFG"[i] if i < 7 else "?"
        if probe:
            if register.get(k.get("code")) != k.get("nr"):
                b.f(f"Kapitel {k.get('code')}", f"Code und Nummer {k.get('code')} {k.get('nr')} nicht im Provinzregister (meta.provinzen)")
            continue
        if k.get("code") != soll:
            b.f(f"Kapitel {k.get('nr')}", f"Code {k.get('code')} statt {soll} (lückenlos ab A)")
        if k.get("nr") != (ROEMISCH[i] if i < 8 else "?"):
            b.f(f"Kapitel {k.get('code')}", f"römische Nummer {k.get('nr')} statt {ROEMISCH[i] if i < 8 else '?'}")
        n = len(k.get("abschnitte", []))
        if typ == "werk" and not 3 <= n <= 10:
            b.w(f"Kapitel {k.get('code')}", f"{n} Abschnitte; Standard sind 3 bis 10")
        for j, satz in enumerate(k.get("kompakt", [])):
            rest = satz
            for a in ABKUERZUNGEN:
                rest = rest.replace(a, "")
            rest = re.sub(r"\b\d+\.(?=\s)", "", rest)  # Ordinalzahlen („19. Jahrhundert“) sind kein Satzende
            if re.findall(r"[.!?](?=\s+[A-ZÄÖÜ])", rest):
                b.w(f"Kapitel {k.get('code')} kompakt[{j}]", "mehrere Sätze in einem Eintrag; je Eintrag ein Satz")
    rep = werk.get("repetitorium")
    if typ == "werk" and not 4 <= len(kapitel) + bool(rep) <= 8:
        b.w("Kapitel", f"{len(kapitel)} Kapitel und Repetitorium; Standard sind 5 bis 8 Provinzen")
    if rep is not None:
        if rep.get("code") != "L":
            b.f("repetitorium", "Code L verlangt")
        if not probe and rep.get("nr") != ROEMISCH[min(len(kapitel), 7)]:
            b.f("repetitorium", f"römische Nummer {rep.get('nr')} statt {ROEMISCH[min(len(kapitel), 7)]} (folgt dem letzten Kapitel)")
    elif typ == "werk":
        b.w("repetitorium", "fehlt; die letzte Provinz ist immer L „Repetitorium“")
    prov = werk.get("meta", {}).get("provinzen")
    if prov and not werk.get("meta", {}).get("probesatz"):
        soll = [(k["code"], k["name_de"]) for k in kapitel] + ([("L", rep["name_de"])] if rep else [])
        ist = [(p["code"], p["name_de"]) for p in prov]
        if ist != soll:
            b.f("meta.provinzen", f"Register weicht von Kapiteln ab: {ist} statt {soll}")

    codes = {}
    for kc, a in abschnitte(werk):
        c = a.get("code", "")
        if c[:1] != kc:
            b.f(c, f"Abschnittscode passt nicht zu Kapitel {kc}")
        if c in codes:
            b.f(c, "Abschnittscode doppelt vergeben")
        codes[c] = a
        if len(a.get("titel", "")) > MAX_TITEL:
            b.w(c, f"Titel über {MAX_TITEL} Zeichen; bricht im Abschnittskopf um")
        if typ == "werk" and not a.get("fundstelle") and kc != "L":
            b.w(c, "keine Seiten-, Rz- oder Folienangabe (fundstelle)")
    for kc in {x for x, _ in abschnitte(werk)}:
        nummern = [int(a["code"][1:]) for x, a in abschnitte(werk) if x == kc and a.get("code", "")[1:].isdigit()]
        if nummern != sorted(nummern):
            b.f(f"Kapitel {kc}", "Abschnitte nicht aufsteigend nach Code geordnet (Codes nie umnummerieren)")

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
                if probe and ziel[0] in register:
                    b.h(pfad, f"Verweis [[{ziel}]] auf ein Kapitel außerhalb des Probesatzes")
                else:
                    b.f(pfad, f"Verweis [[{ziel}]] zeigt auf keinen Abschnitt")
    for feld in ("quellenkritik", "lexicon"):
        for i, e in enumerate(werk.get(feld, [])):
            if e.get("abschnitt") and e["abschnitt"] not in codes:
                b.f(f"{feld}[{i}]", f"Abschnitt {e['abschnitt']} existiert nicht")
    n_kf = sum(len(k.get("kontrollfragen", [])) for k in kapitel)
    if typ == "werk" and n_kf < 5:
        b.w("Kontrollfragen", f"{n_kf} im ganzen Werk; Standard sind mindestens 5")
    prot = werk.get("aenderungen") or []
    if typ == "werk" and not prot:
        b.w("Änderungsprotokoll", "leer; mindestens Erstfassung eintragen")
    if prot and prot[-1].get("version") != werk.get("meta", {}).get("version"):
        b.w("Änderungsprotokoll", f"letzter Eintrag gilt Version {prot[-1].get('version')}, Werk ist "
                                  f"{werk.get('meta', {}).get('version')}; Eintrag ergänzen (python3 diff.py alt.json neu.json --eintragen)")
    b.codes = codes
    return codes


# 3 · Bausteine ─────────────────────────────────────────────────────────────
def pruefe_bloecke(werk, b, ordner=None):
    domaene = werk.get("modul", {}).get("domaene")
    typ = werk.get("meta", {}).get("typ", "werk")
    lat = {}
    for ort, x in bloecke(werk):
        t = x.get("typ")
        if t == "tabelle":
            pruefe_tabelle(ort, x, b)
        elif t == "abbildung":
            pruefe_abbildung(ort, x, b, ordner)
        elif t == "rechenweg":
            pruefe_rechenweg(ort, x, b, typ)
        elif t == "spitzmarke":
            if x["art"] == "austriacum" and domaene == "recht":
                b.f(ort, "Austriacum in der Rechtsdomäne unzulässig (Anker ist bereits Österreichbezug)")
            if x["art"] == "luecke":
                b.h(ort, "Lücke (sinngemäß ergänzt); in der Abschlussmeldung nennen")
            if x["art"] == "aktualisierung" and not x.get("datum"):
                b.w(ort, "Aktualisierung ohne Datum (gilt seit)")
        elif t == "latinum":
            key = x.get("lat", "").strip().lower()
            if key in lat:
                b.w(ort, f"Latinum „{x.get('lat')}“ bereits in {lat[key]}")
            lat[key] = ort
        elif t == "formel":
            for v in x.get("variablen", []):
                if not v.get("bedeutung"):
                    b.f(ort, f"Variable {v.get('symbol')} ohne Bedeutung")


def pruefe_tabelle(ort, x, b):
    ort = f"{ort} Tabelle „{x.get('titel')}“"
    n = len(x.get("kopf", []))
    for i, z in enumerate(x.get("zeilen", [])):
        if len(z) != n:
            b.f(ort, f"Zeile {i+1} hat {len(z)} Zellen, Kopf hat {n}")
        if any(not str(zelle).strip() for zelle in z):
            b.w(ort, f"Zeile {i+1} enthält leere Zelle (für „nicht anwendbar“ ausdrücklich „entfällt“ schreiben)")
    for feld in ("spalten", "unterkopf", "spaltenrollen"):
        if x.get(feld) and len(x[feld]) != n:
            b.f(ort, f"{len(x[feld])} Einträge in „{feld}“ für {n} Spalten")
    if n > 7:
        b.f(ort, f"{n} Spalten; im Satzspiegel nicht lesbar, Tabelle teilen")
    elif n > 5:
        b.h(ort, f"{n} Spalten; im Satzspiegel eng, Satz ansehen (Kontaktabzug)")
    if len(x.get("zeilen", [])) >= 3 and not x.get("aussage"):
        b.h(ort, "ohne Aussage (ein Satz, was sie zeigt)")
    if x.get("art") == "vergleich" and n - 1 > 4:
        b.w(ort, "Vergleichstabelle mit mehr als vier Begriffen; teilen")


def pruefe_abbildung(ort, x, b, ordner=None):
    v = x.get("variante")
    ort = f"{ort} Abbildung „{x.get('titel')}“"
    if v == "kurve":
        for r in x.get("reihen", []):
            xs = [p[0] for p in r.get("punkte", [])]
            if xs != sorted(xs) or len(xs) != len(set(xs)):
                b.f(ort, f"Reihe „{r.get('name')}“: x-Werte nicht streng aufsteigend")
        alle_x = [p[0] for r in x.get("reihen", []) for p in r.get("punkte", [])]
        for mk in x.get("markierungen", []):
            if alle_x and not min(alle_x) <= mk["x"] <= max(alle_x):
                b.f(ort, f"Markierung „{mk.get('text')}“ liegt mit x = {mk['x']} außerhalb der x-Achse ({min(alle_x)} bis {max(alle_x)})")
    elif v == "tkonto":
        soll = sum(e["betrag"] for k in x.get("konten", []) for e in k.get("soll", []))
        haben = sum(e["betrag"] for k in x.get("konten", []) for e in k.get("haben", []))
        if abs(soll - haben) > 0.005:
            b.f(ort, f"Soll {soll:,.2f} ≠ Haben {haben:,.2f}")
    elif v == "baum":
        pruefe_baum(ort, x, b)
    elif v == "bild":
        pruefe_bild(ort, x, b, ordner)
    elif v == "svg":
        svg = x.get("svg", "")
        if "viewBox" not in svg:
            b.f(ort, "SVG ohne viewBox; skaliert nicht")
        if RE_HEX.search(svg) or RE_NAMENSFARBE.search(svg):
            b.f(ort, "SVG mit fester Farbe; nur Klassen t-flaeche, t-akzent, t-linie, t-text, t-klein verwenden (Dark Mode)")
        if re.search(r"<script|on[a-z]+=", svg, re.I):
            b.f(ort, "SVG enthält Skript oder Event-Handler")
    if not x.get("nachweis", "").strip():
        b.f(ort, "ohne Nachweis (Quelle oder „Eigene Darstellung“)")


# 3 · Bäume (3.5) ───────────────────────────────────────────────────────────
BAUM_UNTEN_BLAETTER, BAUM_UNTEN_EBENEN = 6, 5
BAUM_RECHTS_BLAETTER, BAUM_RECHTS_EBENEN = 14, 4


def baum_struktur(x):
    """→ (Kinder je Knoten, Wurzeln, Ebene je Knoten, Blätter, Richtung) · Ebene None bei Zyklus."""
    knoten = {k["id"]: k for k in x.get("knoten", [])}
    kinder = {i: [] for i in knoten}
    for k in x.get("knoten", []):
        if k.get("eltern") in kinder:
            kinder[k["eltern"]].append(k["id"])
    wurzeln = [k["id"] for k in x.get("knoten", []) if not k.get("eltern")]
    ebene = {}
    for i in knoten:
        n, j, weg = 1, i, set()
        while knoten[j].get("eltern") in knoten and j not in weg:
            weg.add(j)
            j = knoten[j]["eltern"]
            n += 1
        ebene[i] = None if j in weg else n
    blaetter = [i for i in knoten if not kinder[i]]
    richtung = x.get("richtung") or ("unten" if len(blaetter) <= BAUM_UNTEN_BLAETTER else "rechts")
    return kinder, wurzeln, ebene, blaetter, richtung


def pruefe_baum(ort, x, b):
    ids = [k["id"] for k in x.get("knoten", [])]
    if len(ids) != len(set(ids)):
        b.f(ort, "doppelte Knoten-ID")
        return
    for k in x.get("knoten", []):
        if k.get("eltern") and k["eltern"] not in ids:
            b.f(ort, f"Knoten „{k['id']}“: Elternknoten „{k['eltern']}“ fehlt")
            return
        if k.get("eltern") == k["id"]:
            b.f(ort, f"Knoten „{k['id']}“ ist sein eigener Elternknoten")
            return
        if len(k.get("text", "")) > 70:
            b.w(ort, f"Knoten „{k['id']}“: Text über 70 Zeichen; im Kasten kaum lesbar")
    kinder, wurzeln, ebene, blaetter, richtung = baum_struktur(x)
    if len(wurzeln) != 1:
        b.f(ort, f"{len(wurzeln)} Wurzeln (Knoten ohne eltern); genau eine verlangt")
    if any(e is None for e in ebene.values()):
        b.f(ort, "Kreis in der Hierarchie (Knoten ist sein eigener Vorfahr)")
        return
    for k in x.get("knoten", []):
        if not k.get("eltern") and k.get("label"):
            b.w(ort, f"Wurzel „{k['id']}“ trägt ein Kantenlabel, hat aber keine eingehende Kante")
    tiefe = max(ebene.values())
    if richtung == "unten":
        if len(blaetter) > BAUM_UNTEN_BLAETTER:
            b.f(ort, f"{len(blaetter)} Blätter; Richtung „unten“ trägt höchstens {BAUM_UNTEN_BLAETTER} (richtung „rechts“ setzen)")
        if tiefe > BAUM_UNTEN_EBENEN:
            b.f(ort, f"{tiefe} Ebenen; Richtung „unten“ trägt höchstens {BAUM_UNTEN_EBENEN}")
    else:
        if len(blaetter) > BAUM_RECHTS_BLAETTER:
            b.f(ort, f"{len(blaetter)} Blätter; höchstens {BAUM_RECHTS_BLAETTER}, Baum teilen")
        if tiefe > BAUM_RECHTS_EBENEN:
            b.f(ort, f"{tiefe} Ebenen; Richtung „rechts“ trägt höchstens {BAUM_RECHTS_EBENEN} (richtung „unten“ setzen oder teilen)")


# 3 · Bilder (3.5) ─────────────────────────────────────────────────────────
SATZSPIEGEL_MM = 165          # Breite des Satzspiegels im Lernskript
DPI_MIN, DPI_GUT = 96, 150    # darunter Fehler bzw. Warnung (Bildschirmnutzung mit Zoom)
BILD_MAX, BILD_GROSS = 4_000_000, 1_500_000
RE_LIZENZ = re.compile(r"^(eigenes werk|gemeinfrei|cc0 1\.0|cc by(-nc)?(-sa|-nd)? [234]\.0( [a-z]{2})?"
                       r"|zitat \(§ 42f urhg\)|freies werk \(§ 7 urhg\))$")


def bild_bytes(x, ordner=None):
    """→ (Bytes, MIME, Herkunft) eines Bildbausteins; Bytes None, wenn nicht auffindbar."""
    import base64
    if x.get("daten"):
        kopf, b64 = x["daten"].split(",", 1)
        return base64.b64decode(b64), kopf[5:].split(";")[0], "eingebettet"
    if ordner is None:
        return None, None, x.get("datei")
    pfad = Path(ordner) / x["datei"]
    if not pfad.is_file():
        return None, None, x["datei"]
    endung = pfad.suffix.lower().lstrip(".")
    return pfad.read_bytes(), "image/" + ("jpeg" if endung in ("jpg", "jpeg") else endung), x["datei"]


def lizenz_norm(l):
    return re.sub(r"\s+", " ", l.replace("\u00a0", " ")).strip().lower()


def pruefe_bild(ort, x, b, ordner=None):
    import io
    try:
        roh, mime, herkunft = bild_bytes(x, ordner)
    except Exception:
        b.f(ort, "Bilddaten (base64) nicht lesbar")
        return
    if roh is None:
        if ordner is None:
            b.h(ort, f"Bilddatei „{herkunft}“ nicht geprüft (Ordner der werk.json unbekannt)")
        else:
            b.f(ort, f"Bilddatei „{herkunft}“ nicht gefunden (Pfad relativ zur werk.json)")
        return
    if x.get("datei"):
        b.w(ort, f"Bild als Datei verknüpft ({herkunft}); werk.json ist nicht selbsttragend: python3 bild.py werk.json --einbetten")
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(roh))
        im.load()
    except Exception:
        b.f(ort, "Bild nicht lesbar (beschädigt oder kein Rasterbild)")
        return
    if im.format not in ("PNG", "JPEG", "WEBP"):
        b.f(ort, f"Bildformat {im.format}; erlaubt sind PNG, JPEG und WebP")
    elif mime != "image/" + im.format.lower():
        b.f(ort, f"Bild ist {im.format}, angegeben als {mime}")
    if len(roh) > BILD_MAX:
        b.f(ort, f"Bild {len(roh) / 1e6:.1f} MB; höchstens {BILD_MAX / 1e6:.0f} MB (verkleinern: python3 bild.py werk.json --einbetten)")
    elif len(roh) > BILD_GROSS:
        b.w(ort, f"Bild {len(roh) / 1e6:.1f} MB; Karte und Deck werden schwer (python3 bild.py werk.json --einbetten verkleinert)")
    dpi = im.width / (x.get("breite", 100) / 100 * SATZSPIEGEL_MM / 25.4)
    if dpi < DPI_MIN:
        b.f(ort, f"Auflösung {dpi:.0f} dpi bei {x.get('breite', 100)} % Breite ({im.width} px); mindestens {DPI_MIN} dpi")
    elif dpi < DPI_GUT:
        b.w(ort, f"Auflösung {dpi:.0f} dpi ({im.width} px); unscharf beim Zoomen, empfohlen ab {DPI_GUT} dpi oder geringere Breite")
    lz = lizenz_norm(x.get("lizenz", ""))
    if not RE_LIZENZ.match(lz):
        b.w(ort, f"Lizenz „{x.get('lizenz')}“ nicht erkannt; Nachnutzung prüfen (eigenes Werk, gemeinfrei, CC, Zitat § 42f UrhG, freies Werk § 7 UrhG)")
    if lz.startswith("cc by") and not x.get("urheber"):
        b.f(ort, "CC-BY-Lizenz verlangt Namensnennung: Feld „urheber“ fehlt")


# 3 · Rechenprobe (3.5) ────────────────────────────────────────────────────
def pruefe_rechenweg(c, x, b, typ=None):
    import rechenprobe as R
    pr = x.get("probe")
    if not pr:
        if typ == "werk":
            b.w(c, "Rechenweg ohne Rechenprobe (probe); Ergebnis vom Kit ungeprüft")
        return
    try:
        zeilen, (ist, st) = R.pruefe(pr)
    except R.ProbeFehler as e:
        b.f(c, f"Rechenprobe nicht berechenbar: {e}")
        return
    for nr, ausdruck, wert, soll, ok, stl in zeilen:
        if not ok:
            b.f(c, f"Rechenprobe Zeile {nr}: „{ausdruck}“ ergibt {R.at(wert, stl)}, angegeben {R.at(soll, stl)}")
    text = x.get("ergebnis", "").replace("\u00a0", " ").replace("\u202f", " ")
    if not any(v in text for v in R.at_varianten(ist, st)):
        b.w(c, f"Ergebnistext „{x.get('ergebnis')}“ nennt den nachgerechneten Wert {R.at(ist, st)} nicht")
    if pr.get("quelle"):
        try:
            q = R.runde(R.dez(pr["quelle"]["wert"]), st)
        except R.ProbeFehler as e:
            b.f(c, f"Rechenprobe, Wert der Quelle: {e}")
            return
        if q != ist:
            b.h(c, f"Quelle „{pr['quelle']['kurz']}“ nennt {R.at(q, st)}, richtig {R.at(ist, st)}: Eintrag der Quellenkritik wird automatisch erzeugt")



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
    import skript
    quellen = werk.get("quellen", [])
    kurz = [q.get("kurz") for q in quellen]
    for k in sorted({x for x in kurz if kurz.count(x) > 1}):
        b.f("quellen", f"Kurzzitat „{k}“ doppelt vergeben")
    schluessel = {}
    for i, q in enumerate(quellen):
        for s in skript.quell_schluessel(q):
            if s in schluessel and schluessel[s] != q["kurz"]:
                b.f(f"quellen[{i}]", f"Schlüssel „{s}“ gehört schon zu „{schluessel[s]}“")
            schluessel[s] = q["kurz"]
        g = q.get("gattung")
        if not g:
            b.h(f"quellen[{i}]", f"„{q.get('kurz')}“ im alten Format (nur voll); bei der nächsten Überarbeitung strukturiert erfassen")
            continue
        for feld in PFLICHT.get(g, []):
            felder = feld if isinstance(feld, tuple) else (feld,)
            if not any(q.get(f) for f in felder) and not q.get("voll"):
                b.f(f"quellen[{i}]", f"„{q.get('kurz')}“ ({g}): Pflichtangabe {' oder '.join(felder)} fehlt")
    benutzt = set()
    for c, a in codes.items():
        for z in a.get("quellen", []):
            if z not in kurz:
                b.f(c, f"zitiert „{z}“, das im Quellenverzeichnis fehlt")
            benutzt.add(z)
    for _, t in skript.texte(werk):
        try:
            _, fns = skript.fussnoten_zerlegen(t)
        except ValueError:
            continue  # meldet skript.regeln
        for fn in fns:
            for s in re.findall(r"@([A-Za-z0-9ÄÖÜäöü]+)", fn):
                if s in schluessel:
                    benutzt.add(schluessel[s])
    for e in werk.get("quellenkritik", []):  # „THC (Vorlage)“, „THC, Rz 18“: die Kritik belegt die kritisierte Quelle
        for q in quellen:
            if re.match(re.escape(q["kurz"]) + r"\b", e.get("quelle", "")):
                benutzt.add(q["kurz"])
    for q in quellen:
        if q["kurz"] not in benutzt and q.get("gattung") != "online":
            b.w("quellen", f"„{q['kurz']}“ wird nirgends belegt (Randbeleg ^[@…] oder Abschnittsquelle)")
    if werk.get("meta", {}).get("typ", "werk") == "werk" and not benutzt:
        b.f("quellen", "kein einziger Beleg im Werk; jeder Abschnitt nennt seine Quellen als Randbeleg ^[@Sigle Fundstelle]")


# 4 · Satzregeln des Buchsatzes ─────────────────────────────────────────────
def pruefe_satzregeln(werk, b):
    import skript
    fehler, warn, hinweis = skript.regeln(werk)
    for z in fehler:
        b.fehler.append("FEHLER   " + z)
    for z in warn:
        b.warnungen.append("WARNUNG  " + z)
    for z in hinweis:
        b.hinweise.append("HINWEIS  " + z)


# Referenzwerk: Abdeckung ───────────────────────────────────────────────────
def pruefe_abdeckung(werk, codes, b):
    """Das Referenzwerk (meta.typ „referenz“) muss jeden Baustein, jede Variante und jeden Sonderfall des Satzes zeigen."""
    if werk.get("meta", {}).get("typ") != "referenz":
        return
    alle = [x for _, x in bloecke(werk)]
    typen = {x.get("typ") for x in alle}
    for t in BLOCKTYPEN:
        if t not in typen:
            b.f("Abdeckung", f"Baustein „{t}“ fehlt im Referenzwerk")
    abb = [x for x in alle if x.get("typ") == "abbildung"]
    for v in VARIANTEN:
        if v not in {x.get("variante") for x in abb}:
            b.f("Abdeckung", f"Abbildung der Variante „{v}“ fehlt")
    for st in ("fluss", "bpmn"):
        if not any(x.get("variante") == "diagramm" and x.get("stil", "fluss") == st for x in abb):
            b.f("Abdeckung", f"kein Diagramm im Stil „{st}“")
    arten = {x.get("art") for x in alle if x.get("typ") == "spitzmarke"}
    for a in SPITZMARKEN:
        if a not in arten:
            b.f("Abdeckung", f"keine Spitzmarke der Art „{a}“")
    tabellen = [x for x in alle if x.get("typ") == "tabelle"]
    for art in ("uebersicht", "vergleich"):
        if not any(x.get("art", "uebersicht") == art for x in tabellen):
            b.f("Abdeckung", f"keine Tabelle der Art „{art}“")
    rollen = {r for x in tabellen for r in x.get("spalten", [])}
    for r in ("begriff", "text", "stichworte", "zahl"):
        if r not in rollen:
            b.f("Abdeckung", f"keine Tabellenspalte mit Rolle „{r}“")
    if not any(len(x.get("zeilen", [])) > LANGE_TABELLE for x in tabellen):
        b.f("Abdeckung", f"keine Tabelle mit mehr als {LANGE_TABELLE} Zeilen (Seitenlauf mit wiederholtem Kopf)")
    if not any(x.get("lesehilfe") for x in alle):
        b.f("Abdeckung", "keine Einbettung mit Lesehilfe")
    baeume = [x for x in abb if x.get("variante") == "baum"]
    for r in ("unten", "rechts"):
        if r not in {baum_struktur(x)[4] for x in baeume}:
            b.f("Abdeckung", f"kein Baum in Richtung „{r}“")
    if not any(k.get("art") == "neben" for x in baeume for k in x.get("knoten", [])):
        b.f("Abdeckung", "kein Baumknoten der Art „neben“")
    if not any(k.get("label") for x in baeume for k in x.get("knoten", [])):
        b.f("Abdeckung", "kein Baum mit Kantenlabel")
    if not any(x.get("markierungen") for x in abb if x.get("variante") == "kurve"):
        b.f("Abdeckung", "keine Kurve mit Markierung")
    proben = [x["probe"] for x in alle if x.get("typ") == "rechenweg" and x.get("probe")]
    if not proben:
        b.f("Abdeckung", "kein Rechenweg mit Rechenprobe")
    if not any(p.get("quelle") for p in proben):
        b.f("Abdeckung", "keine Rechenprobe mit abweichender Quelle (automatische Quellenkritik)")
    if not any(x.get("variablen") for x in alle if x.get("typ") == "formel"):
        b.f("Abdeckung", "keine Formel mit Variablenliste")
    if not any(x.get("typ") == "kern" and any(isinstance(p, dict) and p.get("wichtig") for p in x["punkte"]) for x in alle):
        b.f("Abdeckung", "kein Kernlistenpunkt mit „wichtig“")
    if not any(a.get("wichtig") for a in codes.values()):
        b.f("Abdeckung", "kein Abschnitt mit „wichtig“ (Schlüssel am Abschnittskopf)")
    texte = " ".join(s for _, s in alle_strings(werk))
    if not re.search(r"\[\[[A-Z]{2,5}:", texte):
        b.f("Abdeckung", "kein terraübergreifender Verweis")
    if not re.search(r"\^\[[^\]]*@[A-Za-z0-9ÄÖÜäöü]+\s*\(", texte):
        b.f("Abdeckung", "kein Randbeleg mit Fundstelle (^[@Sigle (Seite)])")
    for k in ("kontrollfragen",):
        if not any(kap.get(k) for kap in werk.get("kapitel", [])):
            b.f("Abdeckung", "keine Kontrollfragen")
    if not any(isinstance(x, dict) for kap in werk.get("kapitel", []) for x in kap.get("einleitung", [])):
        b.f("Abdeckung", "keine Kapiteleinleitung mit Baustein (Übersichtsgrafik)")
    if not any(kap.get("abschluss") for kap in werk.get("kapitel", [])):
        b.f("Abdeckung", "kein Kapitelabschluss („Auf einen Blick“)")
    for feld in ("lexicon", "quellenkritik", "aenderungen", "abkuerzungen", "personen", "rollen"):
        if not werk.get(feld):
            b.f("Abdeckung", f"„{feld}“ fehlt oder ist leer")
    if not (werk.get("repetitorium") or {}).get("abschnitte"):
        b.f("Abdeckung", "Repetitorium ohne eigene Abschnitte (L1 …)")


def validiere(werk, ordner=None):
    b = Bericht()
    pruefe_struktur(werk, b)
    if b.fehler:  # ohne gültige Struktur sind die weiteren Stufen nicht verlässlich
        return b
    pruefe_typografie(werk, b)
    codes = pruefe_kapitel(werk, b)
    pruefe_bloecke(werk, b, ordner)
    pruefe_quellen(werk, codes, b)
    pruefe_satzregeln(werk, b)
    pruefe_formeln(werk, b)
    pruefe_abdeckung(werk, codes, b)
    return b


# ── Exam ──────────────────────────────────────────────────────────────────
def validiere_exam(exam, werk, ordner=None):
    """Prüft ein Exam gegen schema_exam.json, die Regeln des Exam-Standards und das zugehörige Werk (Standard 4.0).
    ordner: Verzeichnis der exam.json (verknüpfte Bilddateien einer Grafik)."""
    b = Bericht()
    if str(exam.get("standard")) != STANDARD:
        b.f("standard", f"Exam im Standard „{exam.get('standard')}“; verlangt {STANDARD} (python3 umsetzen.py --exam alt.json neu.json)")
        return b
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
    codes = {a["code"]: kc for kc, a in abschnitte(werk)}
    provinzen = [k["code"] for k in werk["kapitel"]] + (["L"] if werk.get("repetitorium") else [])
    dims = werk["modul"]["pruefdimensionen"]
    n = len(fragen)
    if not 24 <= n <= 30:
        b.f("Fragen", f"{n} Fragen; verlangt sind 24 bis 30")
    ids = [f["id"] for f in fragen]
    if ids != [f"q{i}" for i in range(1, n + 1)]:
        b.f("Fragen", "IDs nicht fortlaufend q1, q2, …")
    ws = json.loads((HIER / "schema.json").read_text(encoding="utf-8"))
    gv = jsonschema.Draft202012Validator({"$ref": "#/$defs/block", "$defs": ws["$defs"]})
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
        for k in f["abschnitte"]:
            if k not in codes:
                b.f(ort, f"Abschnitt {k} existiert im Werk nicht")
        if f["abschnitte"] and all(codes.get(k) != f["provinz"] for k in f["abschnitte"]):
            b.w(ort, f"keiner der Abschnitte {f['abschnitte']} liegt in Kapitel {f['provinz']}")
        if f["dimension"] not in dims:
            b.f(ort, f"Prüfdimension „{f['dimension']}“ nicht im Domänenmodul ({', '.join(dims)})")
        if werk["modul"]["domaene"] in ("recht", "gemischt"):
            for o in f["optionen"]:
                if not o.get("norm"):
                    b.h(ort + o["id"], "Begründung ohne Normzitat")
        if f.get("grafik"):  # Grafik zum Sachverhalt: eine Abbildung wie im Werk, gleiche Regeln
            g = {"typ": "abbildung", "id": f"grafik_{ort}", **f["grafik"]}
            if not f.get("sachverhalt"):
                b.f(ort, "Grafik ohne Sachverhalt; die Grafik veranschaulicht stets einen Sachverhalt")
            fehler = [e for e in gv.iter_errors(g) if e.validator not in ("allOf", "if")]
            for e in fehler:
                b.f(ort + " Grafik", e.message[:200])
            if not fehler:
                pruefe_abbildung(ort, g, b, ordner)
    fall = sum(1 for f in fragen if f.get("sachverhalt"))
    if fall * 3 < n * 2:
        b.f("Fallquote", f"{fall} von {n} Fragen mit Sachverhalt; verlangt sind mindestens zwei Drittel")
    mehr = sum(1 for f in fragen if f["typ"] == "mehrfach")
    if not 0.35 <= mehr / max(n, 1) <= 0.65:
        b.w("Mischung", f"{mehr} von {n} Mehrfachauswahlfragen; Standard etwa die Hälfte")
    for p in provinzen:
        z = sum(1 for f in fragen if f["provinz"] == p)
        if p != "L" and z < 2:
            b.f("Abdeckung", f"Kapitel {p} nur {z}-mal geprüft (mindestens zweimal)")
    for d in dims:
        z = sum(1 for f in fragen if f["dimension"] == d)
        if z < 3:
            b.f("Abdeckung", f"Prüfdimension „{d}“ nur {z}-mal (mindestens dreimal)")
    zahl = {d: sum(1 for f in fragen if f["dimension"] == d) for d in dims}
    if zahl and min(zahl.values()) > 0 and max(zahl.values()) > 2 * min(zahl.values()):
        hoch, tief = max(zahl, key=zahl.get), min(zahl, key=zahl.get)
        b.w("Ausgewogenheit", f"Prüfdimension „{hoch}“ {zahl[hoch]}-mal, „{tief}“ nur {zahl[tief]}-mal "
                              "(höchstens das Doppelte der seltensten Dimension)")
    for pfad, s in alle_strings(exam):
        if ist_roh(pfad):
            continue
        for zeichen, name in STRICHE.items():
            if zeichen in s:
                b.f(pfad, f"{name} (Gedankenstrich verboten)")
        if '"' in s:
            b.f(pfad, 'gerades Anführungszeichen ("), typografisch „…“ verwenden')
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
        b = validiere_exam(exam, werk, Path(args[0]).resolve().parent)
        print(f"Terra-Validator {VERSION} · {exam.get('meta', {}).get('titel')} zu {werk['meta']['titel']}")
        if hasattr(b, "kennzahlen"):
            k = b.kennzahlen
            print(f"{k['fragen']} Fragen, {k['fallbeispiele']} mit Sachverhalt, {k['mehrfach']} Mehrfachauswahl")
            dims = werk["modul"]["pruefdimensionen"]
            print("Prüfungsmatrix (Kapitel × Dimension):")
            print("      " + " ".join(f"{d[:10]:>11}" for d in dims))
            for p, z in b.matrix.items():
                print(f"  {p}   " + " ".join(f"{z[d]:>11}" for d in dims))
        for z in b.fehler + b.warnungen + b.hinweise:
            print(z)
        print(f"Ergebnis: {len(b.fehler)} Fehler, {len(b.warnungen)} Warnungen, {len(b.hinweise)} Hinweise")
        sys.exit(1 if b.fehler or (streng and b.warnungen) else 0)
    if len(args) != 1:
        sys.exit("Aufruf: python3 validate.py werk.json [--streng]  oder  validate.py exam.json werk.json")
    werk = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    b = validiere(werk, Path(args[0]).resolve().parent)
    typen = sorted({x.get("typ") for _, x in bloecke(werk)}) if not b.fehler or b.codes else []
    print(f"Terra-Validator {VERSION} · {werk.get('meta', {}).get('titel')} · "
          f"{len(werk.get('kapitel', []))} Kapitel{' und Repetitorium' if werk.get('repetitorium') else ''}, {len(b.codes)} Abschnitte")
    if typen:
        print(f"Bausteintypen: {', '.join(typen)}")
    for z in b.fehler + b.warnungen + b.hinweise:
        print(z)
    print(f"Ergebnis: {len(b.fehler)} Fehler, {len(b.warnungen)} Warnungen, {len(b.hinweise)} Hinweise")
    sys.exit(1 if b.fehler or (streng and b.warnungen) else 0)


if __name__ == "__main__":
    main()
