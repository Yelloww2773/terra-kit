/* (c) Oliver Bedernik · Terra-Kit · umbruch.js · Globaler Seitenumbruch (Kit 3.6)
   Reine Rechnung ohne DOM: läuft in Chromium (Montage) und in Node (Tests).

   Eingabe ist ein gemessenes Modell einer Strecke (Folge von Einheiten zwischen zwei festen Umbrüchen):
     C            nutzbare Höhe des Satzspiegels (px)
     of           Höhe des Fortsetzungskopfs einer Kachel (px)
     minZeilen    Mindestzahl Tabellenzeilen je Teil
     einheiten[]  { key: Kachelcode oder null,
                    h: [Höhe je Stufe] (Stufe 0 = volle Größe; weitere Stufen nur bei Abbildungen),
                    strafe: [Strafpunkte je Stufe],
                    tab: null oder { hf0, hc0, hw, delta, zeilen: [Zeilenhöhen] } (teilbare Tabelle),
                    oben, unten: Innenabstand der Kachel über der ersten und unter der letzten Einheit,
                    gapNach: Abstand zur nächsten Einheit (in derselben Kachel oder zum nächsten Block) }
   Gesucht ist die Umbruchfolge mit den geringsten Gesamtkosten (dynamische Programmierung über die
   zulässigen Bruchstellen, Muster Knuth-Plass). Die Kosten einer Seite hängen nur von ihr selbst ab;
   die Wahl der Abbildungsstufen ist seitenlokal und vergrößert den Zustandsraum daher nicht.

   Gewichte (fest im Code, keine Stellschraube in werk.json; Begründung in GEWICHTE):
*/
(function (wurzel) {
  'use strict';

  /* Abgestimmt an Terra Concurrentiae, Exemplaris und Historica (Phase 6, Front im Bericht).
     leer      quadratisch: eine halb leere Seite kostet 25, zwei zu 80 % gefüllte zusammen 8.
               Die letzte Seite vor einem festen Umbruch ist frei (wie die letzte Zeile eines Absatzes).
     teilung   eine Kachel über eine Seitengrenze: so hoch, dass erst eine Seite mit mehr als rund
               55 % Leerraum eine Teilung rechtfertigt; darunter wird die Kachel ganz verschoben.
     kleinrest Fortsetzung aus einem einzigen Baustein unter 20 % des Satzspiegels: praktisch verboten
               (3.7: 1000, damit auch eine halb leere Seite samt Dreiviertelzuschlag billiger bleibt).
               Mehrere kleine Bausteine unter 20 % kosten anteilig bis zur Hälfte (sie sind ein Rest,
               aber kein einzelner verwaister Kasten).
     anriss    Kachelanfang aus Kopf und einem Baustein unter 20 % am Seitenende: wie der Kleinrest.
     nurkopf   Provinzkopf allein auf der Seite: wie der Kleinrest.
     dreiviertel  (3.7) Seite unter 75 %: anteilig bis zum vollen Gewicht bei 50 % (abgestimmt: 250); mit der
               billigeren Teilung an schwachen Bindungen füllt das die Seiten, ohne an starken zu teilen.
     bindung   (3.7) Faktor auf die Teilung je nach Naht: vor Kästen und Fallbeispielen 0,5 (schwach),
               Definition vor Kern oder Formel, Formel vor Rechenweg, Rechenweg vor Abbildung 2 (stark).
     haelfte   Seite unter 50 % Füllstand (außer vor einem festen Umbruch): zusätzlich und hoch, damit eine
               Teilung den Vorzug erhält; quadratisch allein (30 bei 45 %) wöge eine Teilung nicht auf.
     tabelle   Teilung einer Tabelle außerhalb einer Kachel (Repetitorium, Anhang): mäßig.
     stufe     je 10 % Verkleinerung einer Abbildung: gering; Verkleinern nur, wenn es eine Teilung
               oder eine Seite erspart.
     seite     je Seite: gering; bricht Gleichstände zugunsten des kürzeren Satzes. */
  const GEWICHTE = Object.freeze({ leer: 100, teilung: 40, kleinrest: 1000, anriss: 1000, nurkopf: 1000, haelfte: 200, dreiviertel: 250, tabelle: 8, stufe: 2, seite: 1 });
  const BOXEN = new Set(['merke', 'feinheit', 'klausurfalle', 'austriacum', 'aktualisierung', 'latinum', 'luecke', 'beispiel']);
  const STARK = new Set(['definition>kern', 'definition>formel', 'kern>formel', 'formel>formel', 'formel>rechenweg', 'rechenweg>schema']);
  function bindung(a, b) {
    if (!a || !b || a === b) return 1;
    if (BOXEN.has(b.bs)) return 0.5;
    if (STARK.has(a.bs + '>' + b.bs)) return 2;
    return 1;
  }
  const KLEIN = 0.20;      /* Schwelle für Kleinrest und Anriss: Anteil am Satzspiegel */
  const NOTFALL = 1e6;     /* eine Einheit, die auf keine leere Seite passt */

  function atome(m) {
    const a = [];
    m.einheiten.forEach((u, i) => {
      const n = u.tab ? u.tab.zeilen.length : 0;
      if (n) {
        for (let r = 0; r < n; r++) a.push({ u: i, r, bruch: r === 0 || (r >= m.minZeilen && n - r >= m.minZeilen) });
      } else a.push({ u: i, r: -1, bruch: true });
    });
    return a;
  }

  /* Abbildungsstufen einer Seite: geringste Strafe, die mindestens `noetig` px einspart. */
  function stufenwahl(figs, noetig) {
    let best = null;
    const wahl = new Array(figs.length).fill(0);
    (function rek(i, red, strafe) {
      if (best && strafe >= best.strafe) return;
      if (red >= noetig) { best = { strafe, red, wahl: wahl.slice() }; return; }
      if (i === figs.length) return;
      for (let k = 0; k < figs[i].red.length; k++) {
        wahl[i] = k; rek(i + 1, red + figs[i].red[k], strafe + figs[i].strafe[k]);
      }
      wahl[i] = 0;
    })(0, 0, 0);
    return best;
  }

  /* Bewertet die Seite aus den Atomen s bis e (ausschließlich). */
  function bewerte(m, A, s, e, g, n) {
    const E = m.einheiten, C = m.C;
    let H = 0, k = s, prev = -1;
    const segs = [], figs = [];
    const fort = E[A[s].u].key !== null && (s > 0 ? E[A[s - 1].u].key === E[A[s].u].key : !!m.startFort);
    while (k < e) {
      const a = A[k], u = E[a.u];
      let k2 = k;
      while (k2 + 1 < e && A[k2 + 1].u === a.u) k2++;
      let h;
      if (a.r >= 0) {
        const t = u.tab, r1 = A[k2].r;
        let sum = 0;
        for (let r = a.r; r <= r1; r++) sum += t.zeilen[r];
        h = (a.r === 0 ? t.hf0 : t.hc0) + sum + t.delta + (r1 < t.zeilen.length - 1 ? t.hw : (t.ht || 0));
      } else {
        h = u.h[0];
        if (u.h.length > 1) figs.push({ u: a.u, red: u.h.map(x => u.h[0] - x), strafe: u.strafe });
      }
      const neuesSeg = prev < 0 || u.key === null || u.key !== E[prev].key;
      if (neuesSeg) {
        if (prev >= 0) { segs[segs.length - 1].h += E[prev].unten; H += E[prev].unten + E[prev].gapNach; }
        const kopf = u.oben + (segs.length === 0 && fort ? m.of : 0);
        segs.push({ key: u.key, h: kopf + h, fort: segs.length === 0 && fort, start: k, n: 1 });
        H += kopf + h;
      } else {
        segs[segs.length - 1].h += E[prev].gapNach + h; segs[segs.length - 1].n++;
        H += E[prev].gapNach + h;
      }
      prev = a.u; k = k2 + 1;
    }
    segs[segs.length - 1].h += E[prev].unten; H += E[prev].unten;
    const offen = e < n && E[A[e - 1].u].key !== null && E[A[e - 1].u].key === E[A[e].u].key;
    const tabTeil = e < n && A[e].u === A[e - 1].u && A[e].r > 0;
    let wahl = null, red = 0, strafe = 0, notfall = false;
    if (H > C) {
      const w = figs.length ? stufenwahl(figs, H - C) : null;
      if (w) { wahl = w.wahl; red = w.red; strafe = w.strafe; }
      else notfall = true;
    }
    const minH = H - figs.reduce((x, f) => x + Math.max(...f.red), 0);
    const fuell = (H - red) / C;
    let kosten = g.seite + strafe * g.stufe;
    if (e < n) kosten += g.leer * Math.pow(Math.max(0, 1 - fuell), 2) + (fuell < 0.5 ? g.haelfte : 0)
                         + (fuell < 0.75 ? g.dreiviertel * Math.min(1, (0.75 - fuell) / 0.25) : 0);
    if (offen) kosten += g.teilung * (A[e].u === A[e - 1].u ? 1 : bindung(E[A[e - 1].u], E[A[e].u]));
    else if (tabTeil) kosten += g.tabelle;
    const erst = segs[0], letzt = segs[segs.length - 1];
    const restSeg = erst.fort && !(segs.length === 1 && offen) ? erst : null;
    const anrissSeg = offen && !(segs.length === 1 && erst.fort) ? letzt : null;
    const rest = x => x && x.h < KLEIN * C ? (x.n === 1 ? 1 : 0.5 * (KLEIN * C - x.h) / (KLEIN * C)) : 0;
    const kleinrest = !!restSeg && restSeg.n === 1 && restSeg.h < KLEIN * C;
    const anriss = !!anrissSeg && anrissSeg.n === 1 && anrissSeg.h < KLEIN * C;
    kosten += g.kleinrest * rest(restSeg) + g.anriss * rest(anrissSeg);
    const nurKopf = e < n && segs.every(x => x.key === null) && E[A[s].u].kopf;
    if (nurKopf) kosten += g.nurkopf;
    if (notfall) kosten += NOTFALL;
    return { s, e, H, minH, fuell, kosten, notfall, offen, kleinrest, anriss, wahl: wahl ? figs.map((f, i) => [f.u, wahl[i]]).filter(x => x[1] > 0) : [] };
  }

  /* Optimale Umbruchfolge ab Atom `start`. opts.verboten: Menge „s,e“ von Seiten, die beim Setzen
     übergelaufen sind (Messabweichung); sie werden ausgeschlossen. */
  function plane(m, gewichte, opts) {
    const g = Object.assign({}, GEWICHTE, gewichte || {});
    const A = atome(m), n = A.length;
    const start = (opts && opts.start) || 0, verboten = (opts && opts.verboten) || new Set();
    if (n === 0 || start >= n) return { seiten: [], kosten: 0, atome: A };
    const brueche = [start];
    for (let k = start + 1; k < n; k++) if (A[k].bruch) brueche.push(k);
    brueche.push(n);
    const f = new Array(brueche.length).fill(Infinity), vor = new Array(brueche.length).fill(-1), info = new Array(brueche.length).fill(null);
    f[0] = 0;
    for (let j = 1; j < brueche.length; j++) {
      const e = brueche[j];
      for (let i = j - 1; i >= 0; i--) {
        const s = brueche[i];
        if (f[i] === Infinity) continue;
        if (verboten.has(s + ',' + e) && i < j - 1) continue;
        const b = bewerte(m, A, s, e, g, n);
        if (b.notfall && i < j - 1) { if (b.minH > m.C) break; continue; }
        const c = f[i] + b.kosten;
        if (c < f[j] - 1e-9) { f[j] = c; vor[j] = i; info[j] = b; }
      }
    }
    const seiten = [];
    for (let j = brueche.length - 1; j > 0; j = vor[j]) {
      if (vor[j] < 0) throw new Error('Umbruch: keine zulässige Folge');
      seiten.unshift(info[j]);
    }
    return { seiten, kosten: f[brueche.length - 1], atome: A };
  }

  /* Kennzahlen eines Plans (Schätzung aus dem Modell, für die Front im Bericht) */
  function kennzahlen(plan) {
    const S = plan.seiten;
    const voll = S.slice(0, -1);
    return {
      seiten: S.length,
      teilungen: S.filter(x => x.offen).length,
      kleinreste: S.filter(x => x.kleinrest).length,
      anrisse: S.filter(x => x.anriss).length,
      fuell_summe: voll.reduce((a, x) => a + Math.min(1, x.fuell), 0),
      fuell_n: voll.length,
    };
  }

  const api = { GEWICHTE, KLEIN, atome, bewerte, plane, kennzahlen, bindung };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else wurzel.TerraUmbruch = api;
})(typeof window !== 'undefined' ? window : globalThis);
