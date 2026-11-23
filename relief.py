"""(c) Oliver Bedernik · Terra-Kit 4.0 (Entwurf) · Relief: Höhenlinien als Erkennungszeichen der Terra-Reihe.

Ein Gelände aus wenigen Hügeln und Senken, deren Lage allein aus dem Werktitel folgt (gleicher Titel, gleiches Relief).
Es zeigt nichts aus dem Stoff und passt deshalb zu jedem Themenkorb; „Terra“ wird als Landkarte gelesen.
Höhenlinien nach dem Verfahren der laufenden Quadrate (marching squares), zu Linienzügen verbunden und nach
Chaikin geglättet; jede fünfte Linie als Zähllinie kräftiger, wie auf topografischen Karten. Ohne Fremdpakete.
"""
import hashlib
import math
import random

# Kanten einer Zelle: 0 oben, 1 rechts, 2 unten, 3 links; Fall = Bits der Ecken (oben links 8, oben rechts 4, unten rechts 2, unten links 1)
_FAELLE = {1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(0, 1)], 6: [(0, 2)], 7: [(3, 0)], 8: [(3, 0)], 9: [(0, 2)],
           11: [(0, 1)], 12: [(3, 1)], 13: [(2, 1)], 14: [(3, 2)]}


def gelaende(titel, breite, hoehe, schritt=2.6):
    """Höhenfeld (Liste von Zeilen) in mm-Raster; Hügel und Senken aus dem Titel abgeleitet."""
    zufall = random.Random(int(hashlib.sha256(titel.encode("utf-8")).hexdigest()[:12], 16))
    huegel = []
    for i in range(11):  # drei große Erhebungen, vier mittlere, vier kleine Kuppen oder Mulden
        groesse = 0 if i < 3 else (1 if i < 7 else 2)
        huegel.append((zufall.uniform(-0.1, 1.1) * breite, zufall.uniform(-0.1, 1.1) * hoehe,
                       (zufall.uniform(55, 95), zufall.uniform(22, 40), zufall.uniform(9, 16))[groesse],
                       zufall.choice((1, 1, -1)) * (zufall.uniform(0.8, 1.2), zufall.uniform(0.3, 0.55), zufall.uniform(0.08, 0.16))[groesse]))
    kx, ky = zufall.uniform(0.012, 0.022), zufall.uniform(0.012, 0.022)
    phase = zufall.uniform(0, math.tau)
    nx, ny = int(breite / schritt) + 2, int(hoehe / schritt) + 2
    feld = []
    for j in range(ny):
        y = j * schritt
        zeile = []
        for i in range(nx):
            x = i * schritt
            v = sum(a * math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (2 * s * s)) for hx, hy, s, a in huegel)
            v += 0.18 * math.sin(kx * x + phase) * math.cos(ky * y - phase)
            zeile.append(v)
        feld.append(zeile)
    return feld, schritt


def _linien(feld, schritt, stufe):
    """Höhenlinie einer Stufe als Linienzüge in mm."""
    ny, nx = len(feld), len(feld[0])

    def kante(i, j, k):  # Kennung der Gitterkante, auf der der Punkt liegt (gemeinsam für Nachbarzellen)
        return (("h", i, j), ("v", i + 1, j), ("h", i, j + 1), ("v", i, j))[k]

    def punkt(kid):
        art, i, j = kid
        a = feld[j][i]
        b = feld[j][i + 1] if art == "h" else feld[j + 1][i]
        t = 0.5 if a == b else (stufe - a) / (b - a)
        return ((i + t) * schritt, j * schritt) if art == "h" else (i * schritt, (j + t) * schritt)

    nachbarn = {}
    for j in range(ny - 1):
        for i in range(nx - 1):
            ol, orr, ur, ul = feld[j][i], feld[j][i + 1], feld[j + 1][i + 1], feld[j + 1][i]
            fall = (8 if ol > stufe else 0) | (4 if orr > stufe else 0) | (2 if ur > stufe else 0) | (1 if ul > stufe else 0)
            if fall in (0, 15):
                continue
            if fall in (5, 10):  # Sattel: Mittelwert entscheidet
                mitte = (ol + orr + ur + ul) / 4 > stufe
                paare = [(3, 0), (2, 1)] if (fall == 5) == mitte else [(3, 2), (0, 1)]
            else:
                paare = _FAELLE[fall]
            for a, b in paare:
                ka, kb = kante(i, j, a), kante(i, j, b)
                nachbarn.setdefault(ka, []).append(kb)
                nachbarn.setdefault(kb, []).append(ka)
    zuege, gesehen = [], set()
    for start in [k for k, v in nachbarn.items() if len(v) == 1] + list(nachbarn):
        if start in gesehen:
            continue
        zug, akt, vor = [start], start, None
        gesehen.add(start)
        while True:
            weiter = [n for n in nachbarn[akt] if n != vor and n not in gesehen]
            if not weiter:
                if len(zug) > 2 and start in nachbarn[akt] and vor is not None:
                    zug.append(start)  # geschlossen
                break
            vor, akt = akt, weiter[0]
            gesehen.add(akt)
            zug.append(akt)
        if len(zug) > 3:
            zuege.append([punkt(k) for k in zug])
    return zuege


def _glaetten(zug, runden=2):
    geschlossen = zug[0] == zug[-1]
    for _ in range(runden):
        neu = [] if geschlossen else [zug[0]]
        for (x1, y1), (x2, y2) in zip(zug, zug[1:]):
            neu += [(0.75 * x1 + 0.25 * x2, 0.75 * y1 + 0.25 * y2), (0.25 * x1 + 0.75 * x2, 0.25 * y1 + 0.75 * y2)]
        zug = neu + ([neu[0]] if geschlossen else [zug[-1]])
    return zug


def svg(titel, breite=210, hoehe=297, stufen=30, farbe="currentColor", staerke=0.16, zaehl=0.36, klasse="relief"):
    """Relief als SVG in mm (viewBox = Seite); jede fünfte Linie als Zähllinie."""
    feld, schritt = gelaende(titel, breite, hoehe)
    werte = [v for z in feld for v in z]
    lo, hi = min(werte), max(werte)
    pfade = []
    for n in range(1, stufen):
        stufe = lo + (hi - lo) * n / stufen
        d = " ".join("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in _glaetten(z)) for z in _linien(feld, schritt, stufe))
        if d:
            pfade.append(f'<path class="z" d="{d}" stroke-width="{zaehl}"/>' if n % 5 == 0 else f'<path d="{d}" stroke-width="{staerke}"/>')
    return (f'<svg class="{klasse}" viewBox="0 0 {breite} {hoehe}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<g fill="none" stroke="{farbe}" stroke-linejoin="round" stroke-linecap="round">{"".join(pfade)}</g></svg>')
