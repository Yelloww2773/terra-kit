#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · rechenprobe.py (3.5)

Rechnet jeden Rechenweg nach, der eine Probe trägt (rechenweg.probe), und zwar
dezimal exakt (decimal.Decimal, 34 Stellen, kaufmännische Rundung). Die Probe
steht neben dem Rechenweg und ändert seine Darstellung nicht.

    "probe": {
      "werte":    {"C": 10000, "i": "0.05", "n": 3},
      "rechnung": [{"name": "q",  "ausdruck": "1 + i",     "ergebnis": "1.05"},
                   {"name": "PV", "ausdruck": "C / q ** n", "ergebnis": "8638.38"}],
      "stellen":  2,
      "quelle":   {"kurz": "Online-Zinsrechner (Stand 2026)", "wert": "8638.37"}
    }

Jede Zeile wird ausgewertet, auf ihre Stellen gerundet und mit „ergebnis“
verglichen; benannte Zeilen stehen den folgenden als Variable zur Verfügung.
Weicht die Quelle vom nachgerechneten Endergebnis ab, entsteht automatisch ein
Eintrag der Quellenkritik (Rangordnung: Richtigkeit vor Quellentreue).

Erlaubt sind Zahlen, Variablen, + − · / ** und die Funktionen wurzel, ln, exp,
log10, abs, min, max und runden(x, n). Kein eval, kein Zugriff auf Python.
"""
import ast
import decimal
from decimal import Decimal, ROUND_HALF_UP

KONTEXT = decimal.Context(prec=34, rounding=ROUND_HALF_UP)
RE_NAME = r"^[A-Za-z_][A-Za-z0-9_]*$"


class ProbeFehler(Exception):
    pass


def dez(x):
    """JSON-Zahl oder Zeichenkette → Decimal; Fließkommazahlen über ihre kürzeste Darstellung."""
    if isinstance(x, bool):
        raise ProbeFehler("Wahrheitswert statt Zahl")
    if isinstance(x, (int, float)):
        return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)
    if isinstance(x, str):
        try:
            return Decimal(x.strip().replace(" ", ""))
        except decimal.InvalidOperation:
            raise ProbeFehler(f"„{x}“ ist keine Zahl (Dezimalpunkt verwenden, etwa „0.05“)")
    raise ProbeFehler(f"{x!r} ist keine Zahl")


def runde(x, stellen):
    return x.quantize(Decimal(1).scaleb(-stellen), rounding=ROUND_HALF_UP, context=KONTEXT)


def _fn_runden(x, n=Decimal(0)):
    return runde(x, int(n))


FUNKTIONEN = {
    "wurzel": lambda x: x.sqrt(KONTEXT),
    "ln": lambda x: x.ln(KONTEXT),
    "exp": lambda x: x.exp(KONTEXT),
    "log10": lambda x: x.log10(KONTEXT),
    "abs": lambda x: abs(x),
    "min": lambda *a: min(a),
    "max": lambda *a: max(a),
    "runden": _fn_runden,
}


def werte_aus(ausdruck, variablen):
    """Wertet einen arithmetischen Ausdruck sicher aus (nur Zahlen, Namen, Grundrechenarten, Funktionen)."""
    try:
        baum = ast.parse(ausdruck.replace("·", "*").replace("^", "**").replace("\u2212", "-"), mode="eval")
    except SyntaxError as e:
        raise ProbeFehler(f"Ausdruck „{ausdruck}“ nicht lesbar ({e.msg})")

    def w(k):
        if isinstance(k, ast.Expression):
            return w(k.body)
        if isinstance(k, ast.Constant) and isinstance(k.value, (int, float)) and not isinstance(k.value, bool):
            return dez(k.value)
        if isinstance(k, ast.Name):
            if k.id not in variablen:
                raise ProbeFehler(f"unbekannte Größe „{k.id}“")
            return variablen[k.id]
        if isinstance(k, ast.UnaryOp) and isinstance(k.op, (ast.USub, ast.UAdd)):
            v = w(k.operand)
            return -v if isinstance(k.op, ast.USub) else v
        if isinstance(k, ast.BinOp):
            a, b = w(k.left), w(k.right)
            with decimal.localcontext(KONTEXT):
                if isinstance(k.op, ast.Add):
                    return a + b
                if isinstance(k.op, ast.Sub):
                    return a - b
                if isinstance(k.op, ast.Mult):
                    return a * b
                if isinstance(k.op, ast.Div):
                    if b == 0:
                        raise ProbeFehler("Division durch null")
                    return a / b
                if isinstance(k.op, ast.Pow):
                    if a < 0 and b != b.to_integral_value():
                        raise ProbeFehler("negative Basis mit gebrochenem Exponenten")
                    return a ** b
            raise ProbeFehler(f"Rechenzeichen {type(k.op).__name__} nicht erlaubt")
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and not k.keywords:
            f = FUNKTIONEN.get(k.func.id)
            if not f:
                raise ProbeFehler(f"Funktion „{k.func.id}“ nicht erlaubt (erlaubt: {', '.join(FUNKTIONEN)})")
            try:
                with decimal.localcontext(KONTEXT):
                    return f(*[w(a) for a in k.args])
            except (TypeError, decimal.InvalidOperation) as e:
                raise ProbeFehler(f"{k.func.id}(…) nicht berechenbar: {e}")
        raise ProbeFehler(f"Element {type(k).__name__} in „{ausdruck}“ nicht erlaubt")

    try:
        return w(baum)
    except decimal.InvalidOperation as e:
        raise ProbeFehler(f"„{ausdruck}“ nicht berechenbar ({e.__class__.__name__})")


def at(x, stellen):
    """Österreichische Schreibweise: 8638.376 → „8.638,38“ (Tausenderpunkt, Dezimalkomma)."""
    r = runde(x, stellen)
    t = f"{r:,.{stellen}f}" if stellen > 0 else f"{r:,.0f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


def at_varianten(x, stellen):
    """Schreibweisen, unter denen der Ergebnistext den Wert nennen darf."""
    v = {at(x, stellen), at(x, stellen).replace(".", "")}
    if abs(x) < 10:  # Anteilswert, im Text oft in Prozent
        v |= {at(x * 100, max(stellen - 2, 0)), at(x * 100, stellen)}
    return v


def pruefe(probe):
    """→ (Zeilen, Endwert) · Zeilen: [(Nr, Ausdruck, berechnet, angegeben, ok)] · ProbeFehler bei Unberechenbarem."""
    stellen = int(probe.get("stellen", 2))
    variablen = {}
    for name, wert in probe.get("werte", {}).items():
        variablen[name] = dez(wert)
    zeilen, end = [], None
    for i, z in enumerate(probe["rechnung"], 1):
        st = int(z.get("stellen", stellen))
        roh = werte_aus(z["ausdruck"], variablen)
        soll = dez(z["ergebnis"])
        ist = runde(roh, st)
        zeilen.append((i, z["ausdruck"], ist, soll, ist == runde(soll, st), st))
        if z.get("name"):
            variablen[z["name"]] = roh  # ungerundet weiterrechnen, wie im Taschenrechner
        end = (ist, st)
    return zeilen, end


def kritik(werk):
    """Automatische Einträge der Quellenkritik: Quelle nennt ein anderes Endergebnis als die Probe."""
    out = []
    for p in werk.get("provinzen", []):
        for k in p.get("kacheln", []):
            for b in k.get("bausteine", []):
                pr = b.get("probe") if b.get("typ") == "rechenweg" else None
                if not pr or not pr.get("quelle"):
                    continue
                try:
                    _, (ist, st) = pruefe(pr)
                    q = runde(dez(pr["quelle"]["wert"]), st)
                except ProbeFehler:
                    continue  # meldet der Validator
                if q != ist:
                    out.append({"quelle": pr["quelle"]["kurz"],
                                "befund": f"nennt als Ergebnis {at(q, st)}.",
                                "richtig": f"{at(ist, st)} (Rechenprobe des Terra-Kits, kaufmännisch gerundet).",
                                "kachel": k["code"]})
    return out
