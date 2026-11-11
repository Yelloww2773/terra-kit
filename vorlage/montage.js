/* (c) Oliver Bedernik · Terra-Kit · montage.js · Seitenmontage (Kit 3.6)
   Verteilt atomare Einheiten aus #quelle auf feste Seiten in #buch.
   Seitenarten: deck (Titelseite), titelei (ohne Kolumnentitel), spalten (zweispaltig,
   Inhaltsverzeichnis), normal, quer.
   3.6: Inhaltsseiten (normal, quer) werden je Strecke zwischen zwei festen Umbrüchen global umbrochen:
   Planen (Messsäule, dann umbruch.js), Setzen, Prüfen, bei Messabweichung Reparieren. Abbildungen
   atmen zwischen 75 % und 100 % (Kurven über die Plothöhe bei gleicher Schrift, übrige über die Skala
   mit Mindestschrift 6,5 pt). Scheitert die Planung, setzt das Kit gierig wie in 3.5 und warnt.
   Übrige Seitenarten gierig; Einheiten werden nie geteilt, Ausnahme Tabellen (nur zwischen Zeilen,
   Kopf wiederholt). Danach: Daumenregister, Seitenzahlen, Verzeichnis, Silbentrennung fixieren, Prüfung. */
(async function () {
  await document.fonts.ready;
  const META = JSON.parse(document.getElementById('meta').textContent);
  const PROV = META.provinzen;
  const QUELLE = document.getElementById('quelle');
  const BUCH = document.getElementById('buch');
  const einheiten = Array.from(QUELLE.children);
  const bericht = { seiten: [], teilungen: [], skalierungen: [], fehler: [], warnungen: [], hinweise: [],
                    umbruch: { verfahren: 'global', korrekturen: 0, planung_ms: 0, strecken: 0, fuellungen: [], verursacher: [] } };
  const begonnen = new Set();
  const MIN_ZEILEN = 3, MIN_SKALA = 0.75, TOL = 0.75;
  const MIN_PT = 6.5, ZEITGRENZE_MS = 20000, MAX_KORREKTUREN = 200;
  /* global | gierig; nur für die Testreihe: test-scheitern (Planung scheitert), test-messfehler (Modell um 4 %
     zu niedrig, erzwingt Korrekturen), test-kleinste (jede Abbildung in ihrer kleinsten Stufe) */
  const UMBRUCH = META.umbruch || 'global';
  let seite = null, koerper = null, art = null, akt = null;

  /* Daumenregister: Reiter am rechten Rand, Position nach Provinzreihenfolge */
  function daumen(p, nurAktuelle, oben) {
    const H = p.classList.contains('quer') ? 210 : 297, n = PROV.length, o = oben || 28, u = 30;
    const h = Math.min(30, (H - o - u) / n - 2.5);
    let html = '';
    PROV.forEach((v, i) => {
      if (nurAktuelle && (!akt || akt.code !== v.code)) return;
      const etikett = p.classList.contains('deck') ? '<em><b>Provinz ' + v.nr + '</b>' + v.de + '</em>' : '';
      html += '<div class="daumen farbe-' + v.farbe + '" style="top:' + (o + i * (h + 2.5)).toFixed(1) +
              'mm;height:' + h.toFixed(1) + 'mm"><span>' + v.nr + '</span>' + etikett + '</div>';
    });
    p.insertAdjacentHTML('beforeend', html);
  }

  function neueSeite(a) {
    const p = document.createElement('section');
    p.className = 'page ' + a;
    const rechts = (a === 'normal' || a === 'quer') && akt ? 'Provinz ' + akt.nr + ' · ' + akt.name : '';
    const kopf = '<div class="kopfzeile"><span class="l">' + META.kopf_links + '</span><span class="r">' + rechts + '</span></div>';
    const fuss = '<div class="fusszeile"><span class="l">' + META.fuss_links + '</span><span class="m">(c) Oliver Bedernik</span><span class="r seitennr"></span></div>';
    if (a === 'deck') p.innerHTML = '<div class="koerper"></div>' + '<div class="deckvermerk">(c) Oliver Bedernik</div>';
    else p.innerHTML = kopf + '<div class="koerper"></div>' + fuss;
    BUCH.appendChild(p);
    if (a === 'deck') daumen(p, false, 150);
    else if (a === 'spalten') daumen(p, false);
    else if (a === 'normal' || a === 'quer') daumen(p, true);
    seite = p; koerper = p.querySelector('.koerper'); art = a;
    return p;
  }

  function inhaltUnten() {
    let max = koerper.getBoundingClientRect().top;
    for (const c of koerper.children) max = Math.max(max, c.getBoundingClientRect().bottom);
    return max;
  }
  function ueberlauf() {
    const kb = koerper.getBoundingClientRect();
    if (art === 'spalten') {
      for (const c of koerper.children) {
        for (const r of c.getClientRects()) if (r.right > kb.right + TOL || r.bottom > kb.bottom + TOL) return true;
      }
      return false;
    }
    return inhaltUnten() > kb.bottom + TOL;
  }
  function leer() { return koerper.children.length === 0; }
  function seitenart(u) { return u.dataset.seite || (u.dataset.quer ? 'quer' : 'normal'); }

  function behaelter(u) {
    const code = u.dataset.kachel;
    if (!code) return koerper;
    const letzte = koerper.lastElementChild;
    if (letzte && letzte.classList.contains('kachel') && letzte.dataset.code === code) return letzte;
    const k = document.createElement('div');
    k.className = 'kachel farbe-' + (u.dataset.farbe || 'tinte');
    k.dataset.code = code;
    if (begonnen.has(code)) {
      k.classList.add('fortsetzung');
      k.innerHTML = '<div class="fkopf"><span class="code">' + code + '</span>' + u.dataset.titel + ' <i>(Fortsetzung)</i></div>';
    }
    koerper.appendChild(k);
    return k;
  }
  function zurueck(u, ziel) {
    if (u.parentNode) u.parentNode.removeChild(u);
    if (ziel !== koerper && ziel.querySelectorAll('.unit').length === 0) ziel.remove();
  }
  function versuche(u) {
    const ziel = behaelter(u);
    ziel.appendChild(u);
    if (!ueberlauf()) { if (u.dataset.kachel) begonnen.add(u.dataset.kachel); return true; }
    zurueck(u, ziel);
    return false;
  }
  function passtAufLeereSeite(u) {
    const alt = [seite, koerper, art];
    const probe = neueSeite(alt[2]);
    const ziel = behaelter(u); ziel.appendChild(u);
    const ok = !ueberlauf();
    zurueck(u, ziel);
    probe.remove();
    [seite, koerper, art] = alt;
    return ok;
  }

  function teileTabelle(u) {
    const vorlage = u.cloneNode(true);
    const zeilen = Array.from(u.querySelector('table.teilbar').tBodies[0].rows);
    let rest = zeilen, teil = 0;
    const seitenNr = [];
    while (rest.length) {
      const stueck = vorlage.cloneNode(true);
      if (teil > 0) {
        stueck.querySelectorAll('.kkopf, .vor-tabelle').forEach(e => e.remove());
        stueck.querySelectorAll('[id]').forEach(e => e.removeAttribute('id'));
        const st = stueck.querySelector('.schema-titel');
        if (st) st.insertAdjacentHTML('beforeend', '<span class="forts">(Fortsetzung)</span>');
      }
      const tb = stueck.querySelector('table.teilbar').tBodies[0];
      tb.innerHTML = '';
      const ziel = behaelter(u);
      ziel.appendChild(stueck);
      let n = 0;
      for (const r of rest) {
        tb.appendChild(r);
        if (ueberlauf()) { tb.removeChild(r); break; }
        n++;
      }
      const hatteInhalt = koerper.children.length > 1 || (ziel !== koerper && ziel.querySelectorAll('.unit').length > 1);
      if (n === 0 || (n < MIN_ZEILEN && n < rest.length && hatteInhalt)) {
        zurueck(stueck, ziel);
        if (leer()) { bericht.fehler.push('Tabellenzeile höher als eine Seite: ' + (u.dataset.kachel || u.dataset.name || '?')); return; }
        neueSeite(art);
        continue;
      }
      rest = rest.slice(n);
      if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
      seitenNr.push(BUCH.children.length);
      if (rest.length) {
        stueck.querySelectorAll('.nach-tabelle').forEach(e => e.remove());  /* 3.7: Aussage nur im letzten Teil */
        stueck.insertAdjacentHTML('beforeend', '<div class="weiter">Fortsetzung auf der nächsten Seite</div>');
        while (ueberlauf() && tb.rows.length > 1) { const r = tb.rows[tb.rows.length - 1]; rest.unshift(r); tb.removeChild(r); }
        neueSeite(art);
      }
      teil++;
    }
    bericht.teilungen.push({ kachel: u.dataset.kachel || u.dataset.name, teile: teil, seiten: seitenNr, zeilen: zeilen.length });
  }

  function skaliere(u) {
    const fig = u.querySelector('.skalierbar');
    const ziel = behaelter(u);
    ziel.appendChild(u);
    const h0 = fig.getBoundingClientRect().height;
    const zuviel = inhaltUnten() - koerper.getBoundingClientRect().bottom + 2;
    /* 3.6: bezogen auf die Originalgröße; die Abbildung kann schon in ihrer kleinsten Stufe stehen */
    const jetzt = fig.dataset.stufenart === 'skala' && fig.dataset.skala ? +fig.dataset.skala : 1;
    const skala = Math.max(0.3, jetzt * (h0 - zuviel) / h0);
    setzeSkala(fig, skala);
    if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
    bericht.skalierungen.push({ kachel: u.dataset.kachel, skala: +skala.toFixed(3), seite: BUCH.children.length });
    if (skala < MIN_SKALA) bericht.warnungen.push('Abbildung in ' + u.dataset.kachel + ' auf ' + Math.round(skala * 100) + ' % verkleinert (unter Mindestmaß)');
    if (ueberlauf()) bericht.fehler.push('Abbildung in ' + u.dataset.kachel + ' passt auch verkleinert nicht');
  }

  /* ── Abbildungen: Stufen (3.6) ───────────────────────────────────────────────────────────
     Kurven (.atmend) bringen Fassungen mit niedrigerer Plothöhe mit; die Schrift bleibt gleich.
     Alle übrigen Abbildungen werden einheitlich skaliert, höchstens so weit, dass die kleinste
     Grafikschrift (ohne Wasserzeichen) 6,5 pt nicht unterschreitet. */
  function setzeSkala(fig, s) {
    const el = fig.querySelector('svg:not(.var-aus), img');
    if (!el) return;
    if (el.tagName.toLowerCase() === 'svg' && /mm$/.test(el.style.height || '')) {
      /* feste Höhe (hoehe_mm): über die Höhe skalieren; bis 3.5 blieb hier die Höhe unverändert */
      if (!el.dataset.h0) el.dataset.h0 = parseFloat(el.style.height);
      el.style.height = (s * +el.dataset.h0).toFixed(2) + 'mm';
    } else {
      const basis = +(fig.dataset.breite || 100);
      el.style.width = (s * basis).toFixed(1) + '%';
    }
    fig.dataset.skala = s.toFixed(3);
  }
  function kleinsteSchrift(fig) {
    let min = null;
    fig.querySelectorAll('svg:not(.var-aus) text').forEach(t => {
      if (t.classList.contains('t-wz')) return;
      const fs = parseFloat(getComputedStyle(t).fontSize), m = t.getScreenCTM();
      if (!m || !fs) return;
      const pt = fs * Math.hypot(m.a, m.b) * 0.75;
      if (min === null || pt < min) min = pt;
    });
    return min;
  }
  function stufenVon(fig) {
    if (fig.classList.contains('atmend')) {
      return Array.from(fig.querySelectorAll(':scope > svg')).map(s => ({ art: 'hoehe', wert: +(s.dataset.hf || 1) }))
        .filter(s => s.wert <= 1).sort((a, b) => b.wert - a.wert);
    }
    const pt = kleinsteSchrift(fig);
    const smin = pt === null ? MIN_SKALA : Math.max(MIN_SKALA, Math.min(1, MIN_PT / pt));
    fig.dataset.minPt = pt === null ? '' : pt.toFixed(2);
    const werte = [1, 0.875, smin].filter((v, i, a) => v >= smin - 1e-9 && a.indexOf(v) === i).sort((a, b) => b - a);
    return werte.map(v => ({ art: 'skala', wert: +v.toFixed(3) }));
  }
  function wendeStufe(fig, st) {
    if (st.art === 'hoehe') {
      fig.querySelectorAll(':scope > svg').forEach(s => s.classList.toggle('var-aus', +(s.dataset.hf || 1) !== st.wert));
      fig.dataset.skala = st.wert.toFixed(3); fig.dataset.stufenart = 'hoehe';
    } else { setzeSkala(fig, st.wert); fig.dataset.stufenart = 'skala'; }
  }

  /* ── Messsäule: eine Strecke in Satzspiegelbreite, ohne Seitenhöhe ───────────────────────── */
  function messSeite(a) {
    const p = document.createElement('section');
    p.className = 'page ' + a + ' messung';
    p.style.cssText = 'position:absolute;left:-5000mm;top:0;height:auto;break-after:auto';
    p.innerHTML = '<div class="koerper" style="height:auto"></div>';
    document.body.appendChild(p);
    return p;
  }
  function kapazitaet(a) {
    const p = document.createElement('section');
    p.className = 'page ' + a;
    p.style.cssText = 'position:absolute;left:-5000mm;top:0';
    p.innerHTML = '<div class="koerper"></div>';
    document.body.appendChild(p);
    const h = p.querySelector('.koerper').getBoundingClientRect().height;
    p.remove();
    return h;
  }
  function neueKachel(u) {
    const k = document.createElement('div');
    k.className = 'kachel farbe-' + (u.dataset.farbe || 'tinte');
    k.dataset.code = u.dataset.kachel;
    return k;
  }
  function fkopfHtml(u) {
    return '<div class="fkopf"><span class="code">' + u.dataset.kachel + '</span>' + u.dataset.titel + ' <i>(Fortsetzung)</i></div>';
  }
  function fortsetzungsform(el) {
    el.querySelectorAll('.kkopf, .vor-tabelle').forEach(e => e.remove());
    el.querySelectorAll('[id]').forEach(e => e.removeAttribute('id'));
    const st = el.querySelector('.schema-titel');
    if (st && !st.querySelector('.forts')) st.insertAdjacentHTML('beforeend', '<span class="forts">(Fortsetzung)</span>');
    return el;
  }
  function friereEin(t) {
    if (t.dataset.fest) return;
    const muster = Array.from(t.rows).find(r => r.cells.length && Array.from(r.cells).every(c => c.colSpan === 1 && c.getBoundingClientRect().width > 0));
    if (!muster) return;
    const cg = document.createElement('colgroup');
    for (const c of muster.cells) { const col = document.createElement('col'); col.style.width = c.getBoundingClientRect().width + 'px'; cg.appendChild(col); }
    t.style.width = t.getBoundingClientRect().width + 'px';
    t.insertBefore(cg, t.firstChild);
    t.style.tableLayout = 'fixed';
    t.dataset.fest = '1';
  }

  function messeStrecke(lauf, a, startFort) {
    const mp = messSeite(a), K = mp.querySelector('.koerper');
    const bloecke = [];  /* je Einheit: Container (Kachel oder Einheit selbst) */
    let letzte = null;
    for (const u of lauf) {
      const code = u.dataset.kachel;
      if (code) {
        if (!letzte || letzte.dataset.code !== code) { letzte = neueKachel(u); K.appendChild(letzte); }
        letzte.appendChild(u); bloecke.push(letzte);
      } else { K.appendChild(u); letzte = null; bloecke.push(u); }
    }
    /* Tabellenspalten nach dem Gesamtsatz einfrieren: alle Teile behalten dieselben Spalten,
       und die Zeilenhöhen addieren sich exakt. */
    lauf.forEach(u => { const t = u.querySelector('table.teilbar'); if (t) friereEin(t); });
    const R = lauf.map(u => u.getBoundingClientRect());
    const E = lauf.map((u, i) => {
      const b = bloecke[i], br = b.getBoundingClientRect(), kachel = b !== u;
      const erste = kachel ? b.querySelector(':scope > .unit') : u, letzteU = kachel ? Array.from(b.querySelectorAll(':scope > .unit')).pop() : u;
      const e = { el: u, key: u.dataset.kachel || null, kopf: u.dataset.provstart === '1', bs: u.dataset.bs || null,
        h: [R[i].height], strafe: [0], tab: null, fig: null, stufen: null,
        oben: kachel ? erste.getBoundingClientRect().top - br.top : 0,
        unten: kachel ? br.bottom - letzteU.getBoundingClientRect().bottom : 0, gapNach: 0 };
      if (i + 1 < lauf.length) {
        if (bloecke[i + 1] === b) e.gapNach = R[i + 1].top - R[i].bottom;
        else e.gapNach = bloecke[i + 1].getBoundingClientRect().top - br.bottom;
      }
      return e;
    });
    /* Fortsetzungskopf einmal messen */
    let of = 0;
    const probeK = K.querySelector(':scope > .kachel');
    if (probeK) {
      const u0 = probeK.querySelector(':scope > .unit'), t0 = u0.getBoundingClientRect().top;
      probeK.insertAdjacentHTML('afterbegin', fkopfHtml(u0));
      of = u0.getBoundingClientRect().top - t0;
      probeK.firstElementChild.remove();
    }
    /* Teilbare Tabellen: Kopf als erster Teil, Kopf als Fortsetzung, Hinweiszeile, Zeilen */
    E.forEach((e, i) => {
      const u = e.el, t = u.querySelector('table.teilbar');
      if (!t || !t.tBodies[0] || t.tBodies[0].rows.length < 2) return;
      const zeilen = Array.from(t.tBodies[0].rows);
      const rh = zeilen.map(r => r.getBoundingClientRect().height);
      const vorlage = u.cloneNode(true);
      vorlage.querySelector('table.teilbar').tBodies[0].innerHTML = '';
      const mk = bloecke[i] !== u ? neueKachel(u) : document.createElement('div');
      K.appendChild(mk);
      const m1 = vorlage.cloneNode(true); m1.querySelectorAll('[id]').forEach(x => x.removeAttribute('id')); mk.appendChild(m1);
      const hfMit = m1.getBoundingClientRect().height;
      m1.querySelectorAll('.nach-tabelle').forEach(x => x.remove());  /* 3.7: Aussage steht nur unter dem letzten Teil */
      const hf0 = m1.getBoundingClientRect().height, ht = hfMit - hf0;
      m1.insertAdjacentHTML('beforeend', '<div class="weiter">Fortsetzung auf der nächsten Seite</div>');
      const hw = m1.getBoundingClientRect().height - hf0;
      const m2 = fortsetzungsform(vorlage.cloneNode(true)); m1.replaceWith(m2);
      m2.querySelectorAll('.nach-tabelle').forEach(x => x.remove());
      const hc0 = m2.getBoundingClientRect().height;
      mk.remove();
      e.tab = { hf0, hc0, hw, ht, zeilen: rh, delta: R[i].height - (hf0 + ht + rh.reduce((x, y) => x + y, 0)) };
      e.zeilenEl = zeilen; e.vorlage = vorlage;
    });
    /* Abbildungen: Höhe der Einheit je Stufe */
    E.forEach(e => {
      if (e.tab) return;
      const fig = e.el.querySelector('.fig.skalierbar');
      if (!fig) return;
      let stufen = stufenVon(fig);
      if (UMBRUCH === 'test-kleinste') stufen = [stufen[stufen.length - 1]];
      if (stufen.length < 2) { wendeStufe(fig, stufen[0]); e.h = [e.el.getBoundingClientRect().height]; e.fig = fig; e.stufen = stufen; return; }
      e.h = stufen.map(st => { wendeStufe(fig, st); return e.el.getBoundingClientRect().height; });
      e.strafe = stufen.map(st => Math.round((1 - st.wert) * 100) / 10);
      wendeStufe(fig, stufen[0]);
      e.fig = fig; e.stufen = stufen;
    });
    /* 3.7: größere Kurvenfassung, nur genutzt, wenn auf der fertigen Seite Platz bleibt */
    E.forEach(e => {
      if (!e.fig || !e.fig.classList.contains('atmend') || UMBRUCH === 'test-kleinste') return;
      e.gross = Array.from(e.fig.querySelectorAll(':scope > svg')).map(s => +(s.dataset.hf || 1)).filter(w => w > 1)
        .sort((a, b) => b - a).map(w => ({ art: 'hoehe', wert: w }));
    });
    if (UMBRUCH === 'test-messfehler') E.forEach(e => { e.h = e.h.map(x => x * 0.96); if (e.tab) e.tab.zeilen = e.tab.zeilen.map(x => x * 0.96); });
    return { mp, modell: { C: kapazitaet(a) - 1, of, minZeilen: MIN_ZEILEN, startFort, einheiten: E } };
  }

  /* ── Strecken: Folgen von Inhaltseinheiten zwischen festen Umbrüchen ──────────────────────── */
  function strecken() {
    const S = [];
    let lauf = null;
    einheiten.forEach((u, i) => {
      const sa = seitenart(u), zwang = u.dataset.neueSeite === '1';
      if (u.dataset.fuell === '1') { lauf = null; return; }  /* 3.7: Füllblock, gesetzt nur wenn er passt */
      const inhalt = sa === 'normal' || sa === 'quer';
      if (inhalt && lauf && lauf.art === sa && !zwang) { lauf.einheiten.push(u); return; }
      lauf = inhalt ? { art: sa, start: i, einheiten: [u] } : null;
      if (lauf) S.push(lauf);
    });
    return S;
  }

  /* ── Satz einer geplanten Seite; Rückgabe: passt sie? ──────────────────────────────────────── */
  function setzeGeplant(M, A, pg, a, protokoll) {
    neueSeite(a);
    const E = M.einheiten, neu = [];
    const wahl = new Map(pg.wahl);
    let k = pg.s;
    while (k < pg.e) {
      const at = A[k];
      let k2 = k;
      while (k2 + 1 < pg.e && A[k2 + 1].u === at.u) k2++;
      const e = E[at.u], u = e.el;
      if (e.fig && e.stufen) wendeStufe(e.fig, e.stufen[wahl.get(at.u) || 0]);
      const code = u.dataset.kachel;
      if (code && !begonnen.has(code)) neu.push(code);
      const ziel = behaelter(u);
      if (at.r < 0) {
        ziel.appendChild(u);
        protokoll.push({ e, typ: 'ganz' });
      } else {
        const r1 = A[k2].r, n = e.zeilenEl.length;
        const stueck = at.r === 0 ? u : fortsetzungsform(e.vorlage.cloneNode(true));
        const tb = stueck.querySelector('table.teilbar').tBodies[0];
        if (at.r === 0) tb.innerHTML = '';
        for (let r = at.r; r <= r1; r++) tb.appendChild(e.zeilenEl[r]);
        stueck.querySelectorAll('.nach-tabelle').forEach(x => x.classList.toggle('aus', r1 < n - 1));
        if (r1 < n - 1) stueck.insertAdjacentHTML('beforeend', '<div class="weiter">Fortsetzung auf der nächsten Seite</div>');
        ziel.appendChild(stueck);
        protokoll.push({ e, typ: 'teil', stueck, r0: at.r, r1, n });
        if (!(at.r === 0 && r1 === n - 1)) (e.teile = e.teile || []).push(BUCH.children.length);
      }
      if (code) begonnen.add(code);
      k = k2 + 1;
    }
    return { passt: !ueberlauf(), neu };
  }
  /* Rücknahme einer übergelaufenen Seite (Messabweichung): Einheiten zurück in die Messsäule */
  function nimmZurueck(protokoll, neu, ablage) {
    for (const p of protokoll) {
      if (p.typ === 'ganz') { ablage.appendChild(p.e.el); continue; }
      if (p.e.teile && p.e.teile[p.e.teile.length - 1] === BUCH.children.length) p.e.teile.pop();
      if (p.stueck !== p.e.el) { p.stueck.remove(); continue; }  /* Folgeteil: Zeilen gehen mit, setzeGeplant hängt sie neu ein */
      p.stueck.querySelectorAll(':scope > .weiter').forEach(w => w.remove());
      ablage.appendChild(p.e.el);
    }
    neu.forEach(c => begonnen.delete(c));
    BUCH.lastElementChild.remove();
    const vorher = BUCH.lastElementChild;
    if (vorher) { seite = vorher; koerper = vorher.querySelector('.koerper'); art = ['deck', 'titelei', 'spalten', 'quer'].find(x => vorher.classList.contains(x)) || 'normal'; }
  }

  function setzeStrecke(st) {
    const { M, plan } = st;
    let A = plan.atome, seiten = plan.seiten.slice(), i = 0;
    const verboten = new Set();
    if (st.einheiten[0].dataset.provstart) { const u = st.einheiten[0]; akt = { code: u.dataset.prov, nr: u.dataset.nr, name: u.dataset.pname, farbe: u.dataset.farbe }; }
    while (i < seiten.length) {
      const pg = seiten[i];
      if (pg.notfall && pg.e - pg.s === 1) {  /* passt auf keine leere Seite: wie 3.5 */
        neueSeite(st.art);
        const at = A[pg.s], e = M.einheiten[at.u];
        if (at.r >= 0) bericht.fehler.push('Tabellenzeile höher als eine Seite: ' + (e.el.dataset.kachel || e.el.dataset.name || '?'));
        else if (e.fig) { if (e.stufen) wendeStufe(e.fig, e.stufen[e.stufen.length - 1]); skaliere(e.el); }
        else { behaelter(e.el).appendChild(e.el); bericht.fehler.push('Einheit passt auf keine leere Seite: ' + (e.el.dataset.kachel || e.el.dataset.name || '?')); }
        if (e.el.dataset.kachel) begonnen.add(e.el.dataset.kachel);
        i++; continue;
      }
      const protokoll = [];
      const r = setzeGeplant(M, A, pg, st.art, protokoll);
      if (r.passt) {
        /* 3.7: Platz übrig? Kurven in größerer Fassung; danach Verursacher eines schwachen Füllstands */
        const wahl = new Map(pg.wahl);
        for (const p of protokoll) {
          const e = p.e;
          if (!e.gross || !e.gross.length || (wahl.get(M.einheiten.indexOf(e)) || 0) > 0) continue;
          for (const g of e.gross) { wendeStufe(e.fig, g); if (!ueberlauf()) break; wendeStufe(e.fig, e.stufen[0]); }
        }
        if (pg.e < A.length) {
          const kb = koerper.getBoundingClientRect(), fuell = (inhaltUnten() - kb.top) / kb.height;
          if (fuell < 0.75) {
            /* erste Bruchstelle nach dem Seitenende, bis zu der der Inhalt nicht mehr passt; passte davor
               schon etwas, hielt eine Strafe (meist Anriss oder starke Bindung) den Umbruch zurück */
            let e2 = pg.e, b2 = null, zurueck = false;
            while (e2 < A.length) {
              e2++;
              while (e2 < A.length && !A[e2].bruch) e2++;
              b2 = TerraUmbruch.bewerte(M, A, pg.s, e2, TerraUmbruch.GEWICHTE, A.length);
              if (b2.minH > M.C) break;
              zurueck = true;
            }
            const mm = b2 ? Math.round((b2.minH - M.C) / 3.78) : 0;
            const nx = M.einheiten[A[Math.min(e2, A.length) - 1].u].el;
            if (mm > 0) bericht.umbruch.verursacher.push({ seite: BUCH.children.length, fuellstand: +fuell.toFixed(2),
              kachel: nx.dataset.kachel || nx.dataset.name || '?', fehlen_mm: mm, zurueckgehalten: zurueck });
          }
        }
        i++; continue;
      }
      let innen = false;
      for (let k = pg.s + 1; k < pg.e; k++) if (A[k].bruch) { innen = true; break; }
      if (!innen) {
        /* Nichts Kleineres möglich: eine Einheit, die gemessen passte, im Satz aber nicht (Rundung).
           Abbildung notverkleinern, sonst bleibt der Überlauf stehen und die Prüfung meldet ihn. */
        const e = M.einheiten[A[pg.s].u];
        if (A[pg.s].r < 0 && e.fig && pg.e - pg.s === 1) skaliere(e.el);
        i++; continue;
      }
      /* Messabweichung: Seite zurücknehmen, ausschließen, Rest neu planen */
      bericht.umbruch.korrekturen++;
      if (bericht.umbruch.korrekturen > MAX_KORREKTUREN) throw new Error('zu viele Korrekturen');
      nimmZurueck(protokoll, r.neu, st.mp.querySelector('.koerper'));
      verboten.add(pg.s + ',' + pg.e);
      const neu = TerraUmbruch.plane(M, null, { start: pg.s, verboten });
      seiten = seiten.slice(0, i).concat(neu.seiten);
    }
    M.einheiten.forEach(e => { if (e.teile && e.teile.length) bericht.teilungen.push({ kachel: e.el.dataset.kachel || e.el.dataset.name, teile: e.teile.length, seiten: e.teile, zeilen: e.zeilenEl.length }); });
    st.mp.remove();
  }

  /* Gieriger Satz einer Einheit (Verfahren bis 3.5; Rückfallebene und übrige Seitenarten) */
  function setzeGierig(u) {
    if (u.dataset.fuell === '1') {  /* 3.7: Kernfakten der Provinz nur in den Rest der letzten Seite */
      if (seite && (art === 'normal' || art === 'quer') && !leer()) {
        koerper.appendChild(u);
        if (ueberlauf()) { u.remove(); bericht.umbruch.fuellungen.push({ prov: u.dataset.prov, seite: null }); }
        else bericht.umbruch.fuellungen.push({ prov: u.dataset.prov, seite: BUCH.children.length });
      }
      return;
    }
    if (u.dataset.provstart) akt = { code: u.dataset.prov, nr: u.dataset.nr, name: u.dataset.pname, farbe: u.dataset.farbe };
    const sa = seitenart(u);
    const zwang = u.dataset.neueSeite === '1';
    if (!seite || art !== sa || (zwang && !leer()) || sa === 'deck') {
      if (!(seite && leer() && art === sa)) neueSeite(sa);
    }
    if (versuche(u)) return;
    if (!leer() && passtAufLeereSeite(u)) { neueSeite(art); if (versuche(u)) return; }
    if (u.querySelector('table.teilbar')) { teileTabelle(u); return; }
    if (u.querySelector('.skalierbar')) { if (!leer()) neueSeite(art); skaliere(u); return; }
    const ziel = behaelter(u); ziel.appendChild(u);
    if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
    bericht.fehler.push('Einheit passt auf keine leere Seite: ' + (u.dataset.kachel || u.dataset.name || '?'));
  }

  /* ── Planung aller Strecken; bei Scheitern gierig ─────────────────────────────────────────── */
  const S = UMBRUCH === 'gierig' ? [] : strecken();
  const t0 = performance.now();
  let global = UMBRUCH !== 'gierig';
  try {
    if (UMBRUCH === 'test-scheitern') throw new Error('erzwungenes Scheitern (Testreihe)');
    if (typeof TerraUmbruch === 'undefined') throw new Error('umbruch.js nicht geladen');
    const vorgaenger = new Map();
    einheiten.forEach((u, i) => vorgaenger.set(u, einheiten[i - 1]));
    for (const st of S) {
      const v = vorgaenger.get(st.einheiten[0]);
      const startFort = !!(v && v.dataset.kachel && v.dataset.kachel === st.einheiten[0].dataset.kachel);
      const { mp, modell } = messeStrecke(st.einheiten, st.art, startFort);
      st.mp = mp; st.M = modell;
      st.plan = TerraUmbruch.plane(modell);
      if (performance.now() - t0 > ZEITGRENZE_MS) throw new Error('Zeitgrenze überschritten');
    }
    /* Front: dieselben Strecken mit anderen Teilungsstrafen (Schätzung aus dem Modell) */
    bericht.umbruch.front = [10, 20, 30, 45, 60, 90].map(w => {
      const z = { teilung: w, seiten: 0, teilungen: 0, kleinreste: 0, anrisse: 0, fs: 0, fn: 0 };
      for (const st of S) {
        const k = TerraUmbruch.kennzahlen(w === TerraUmbruch.GEWICHTE.teilung ? st.plan : TerraUmbruch.plane(st.M, { teilung: w }));
        z.seiten += k.seiten; z.teilungen += k.teilungen; z.kleinreste += k.kleinreste; z.anrisse += k.anrisse; z.fs += k.fuell_summe; z.fn += k.fuell_n;
      }
      return { teilung: w, inhaltsseiten: z.seiten, teilungen: z.teilungen, kleinreste: z.kleinreste, anrisse: z.anrisse, fuellstand: z.fn ? +(z.fs / z.fn).toFixed(3) : null };
    });
  } catch (ex) {
    global = false;
    bericht.warnungen.push('Globaler Umbruch gescheitert (' + ex.message + '); gierig gesetzt wie 3.5');
    for (const st of S) { if (st.M) st.M.einheiten.forEach(e => { if (e.fig && e.stufen) wendeStufe(e.fig, e.stufen[0]); }); if (st.mp) st.mp.remove(); st.plan = null; }
  }
  bericht.umbruch.planung_ms = Math.round(performance.now() - t0);
  bericht.umbruch.verfahren = global ? 'global' : 'gierig';
  if (UMBRUCH === 'gierig') bericht.hinweise.push('Umbruch auf Wunsch gierig (--umbruch gierig)');
  bericht.umbruch.strecken = global ? S.length : 0;
  bericht.umbruch.gewichte = global ? TerraUmbruch.GEWICHTE : null;

  /* ── Satz ──────────────────────────────────────────────────────────────────────────────────── */
  const geplant = new Map();
  if (global) S.forEach(st => geplant.set(st.einheiten[0], st));
  try {
    for (let i = 0; i < einheiten.length; i++) {
      const st = geplant.get(einheiten[i]);
      if (st) { setzeStrecke(st); i += st.einheiten.length - 1; continue; }
      setzeGierig(einheiten[i]);
    }
  } catch (ex) {
    bericht.fehler.push('Umbruch: Satz abgebrochen (' + ex.message + ')');
  }
  document.querySelectorAll('section.messung').forEach(m => m.remove());
  QUELLE.remove();

  /* Titelseite: Registerübersicht erst unterhalb des tatsächlichen Titelblocks setzen und
     den verfügbaren Raum bis zur Fußzeile gleichmäßig aufteilen. So kann ein langer Titel,
     Untertitel oder eine lange Lehrveranstaltungszeile die Register nie überlagern. */
  BUCH.querySelectorAll('.page.deck').forEach(p => {
    const mm = 96 / 25.4, pr = p.getBoundingClientRect();
    const titel = p.querySelector('.tp-mitte'), fuss = p.querySelector('.tp-fuss');
    const reiter = Array.from(p.querySelectorAll('.daumen'));
    if (!titel || !reiter.length) return;
    const oben = Math.max(150, (titel.getBoundingClientRect().bottom - pr.top) / mm + 12);
    const unten = fuss ? (fuss.getBoundingClientRect().top - pr.top) / mm - 8 : 267;
    const h = Math.min(30, (unten - oben) / reiter.length - 2.5);
    reiter.forEach((d, i) => { d.style.top = (oben + i * (h + 2.5)).toFixed(1) + 'mm'; d.style.height = h.toFixed(1) + 'mm'; d.classList.toggle('eng', h < 14); });
    if (h < 4.5) bericht.warnungen.push('Titelseite: wenig Platz für die Registerübersicht (' + h.toFixed(1) + ' mm je Reiter)');
  });

  /* Nachbearbeitung: offene Kartenränder, Seitenzahlen, Verzeichnis */
  const karten = Array.from(BUCH.querySelectorAll('.kachel'));
  karten.forEach((k, i) => { const n = karten[i + 1]; if (n && n.dataset.code === k.dataset.code) k.classList.add('offen-unten'); });
  const seiten = Array.from(BUCH.children);
  const N = seiten.length;
  seiten.forEach((p, i) => { const s = p.querySelector('.seitennr'); if (s) s.textContent = 'Seite ' + (i + 1) + ' von ' + N; });
  const seiteVon = el => seiten.indexOf(el.closest('.page')) + 1;
  document.querySelectorAll('[data-ziel]').forEach(span => {
    const z = document.getElementById(span.dataset.ziel);
    if (z) span.textContent = seiteVon(z); else bericht.fehler.push('Verzeichnis: Ziel fehlt ' + span.dataset.ziel);
  });
  /* Sachregister (3.4): je Stichwort doppelte Seiten entfernen, aufsteigend, weiter verlinkt.
     Die Platzhalter „00“ haben die Breite vorab reserviert; die Liste wird nur kürzer. */
  document.querySelectorAll('td.rz').forEach(td => {
    const gesehen = new Map();
    td.querySelectorAll('[data-ziel]').forEach(a => { const n = +a.textContent; if (!gesehen.has(n)) gesehen.set(n, a.dataset.ziel); });
    td.innerHTML = Array.from(gesehen.keys()).sort((x, y) => x - y)
      .map(n => '<a href="#' + gesehen.get(n) + '">' + n + '</a>').join(', ');
  });
  /* Sprungziele für die Lesezeichenleiste (skript.py setzt sie mit pypdf) */
  bericht.anker = {};
  document.querySelectorAll('[id^="k-"], [id^="p-"], [id^="t-"], [id^="a-"]').forEach(e => { bericht.anker[e.id] = seiteVon(e); });
  /* Seiten mit Abbildungen (3.5): Marke im Kontaktabzug für die Sichtprüfung */
  bericht.abbildungsseiten = Array.from(new Set(Array.from(BUCH.querySelectorAll('.fig')).map(seiteVon))).sort((a, b) => a - b);

  /* Silbentrennung fixieren. Am Umbruch rendert Chromium das weiche Trennzeichen
     sichtbar (Breite > 0). Nur dort bleibt ein echter Trennstrich; alle anderen
     Trennstellen werden entfernt, damit der Textlayer durchsuchbar bleibt.
     Reihenfolge ist entscheidend: (1) Tabellenspalten einfrieren, (2) ALLE Trennstellen
     auf dem endgültigen Satz messen, (3) erst dann alle Änderungen anwenden,
     (4) Höhen vorher und nachher vergleichen. */
  const hoehe = () => Array.from(BUCH.querySelectorAll('.unit, .kachel, tr')).map(e => e.getBoundingClientRect().height);
  const h0 = hoehe();
  BUCH.querySelectorAll('table').forEach(t => {
    if (t.dataset.fest) return;  /* 3.6: in der Messsäule eingefroren (alle Teile gleiche Spalten) */
    const muster = Array.from(t.rows).find(r => r.cells.length && Array.from(r.cells).every(c => c.colSpan === 1 && c.getBoundingClientRect().width > 0));
    if (!muster) return;
    const cg = document.createElement('colgroup');
    for (const c of muster.cells) { const col = document.createElement('col'); col.style.width = c.getBoundingClientRect().width + 'px'; cg.appendChild(col); }
    t.style.width = t.getBoundingClientRect().width + 'px';
    t.insertBefore(cg, t.firstChild);
    t.style.tableLayout = 'fixed';
  });
  const h1 = hoehe();
  const diff = (a, b) => a.filter((h, i) => Math.abs(h - b[i]) > 0.5).length;
  const durchEinfrieren = diff(h0, h1);

  const walker = document.createTreeWalker(BUCH, NodeFilter.SHOW_TEXT,
    { acceptNode: n => n.nodeValue.indexOf('\u00AD') >= 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP });
  const plan = [];
  const rg = document.createRange();
  let n; while ((n = walker.nextNode())) {
    const t = n.nodeValue, brueche = new Set();
    for (let i = 0; i < t.length; i++) {
      if (t[i] !== '\u00AD') continue;
      /* Kriterium: Liegen das Zeichen davor und danach auf verschiedenen Zeilen?
         (Die Breite des Trennzeichens allein täuscht bei Ligaturen wie ft, ff, fl.) */
      rg.setStart(n, Math.max(0, i - 1)); rg.setEnd(n, Math.min(t.length, i + 2));
      const zeilen = new Set(Array.from(rg.getClientRects()).filter(r => r.width > 0).map(r => Math.round(r.top)));
      if (zeilen.size > 1) brueche.add(i);
    }
    plan.push([n, brueche]);
  }
  /* Anwenden: Am tatsächlichen Umbruch bleibt das weiche Trennzeichen stehen; das ist
     die Darstellung, die ISO 32000 für Silbentrennung vorsieht (Leser fügen das Wort bei
     Suche und Kopieren wieder zusammen). Ungenutzte Trennstellen werden entfernt.
     Kein Ersatz durch Bindestrich: Das würde den Zeilenumbruch verändern. */
  let trennungen = 0, entfernt = 0;
  for (const [knoten, brueche] of plan) {
    const t = knoten.nodeValue; let neu = '';
    for (let i = 0; i < t.length; i++) {
      if (t[i] !== '\u00AD') { neu += t[i]; continue; }
      if (brueche.has(i)) { neu += t[i]; trennungen++; } else { entfernt++; }
    }
    knoten.nodeValue = neu;
  }
  const h2 = hoehe();
  const durchFixierung = diff(h1, h2);
  const elemente = Array.from(BUCH.querySelectorAll('.unit, .kachel, tr'));
  bericht.verschoben_detail = elemente.map((e, i) => [e, h1[i], h2[i]]).filter(([e, a, b]) => Math.abs(a - b) > 0.5)
    .map(([e, a, b]) => e.tagName + ' ' + (a.toFixed(1)) + '→' + b.toFixed(1) + ' ' + e.textContent.replace(/\s+/g, ' ').slice(0, 90));
  bericht.silbentrennung = { umbrochen: trennungen, entfernt, verschoben_einfrieren: durchEinfrieren, verschoben_fixierung: durchFixierung };
  if (durchEinfrieren) bericht.fehler.push('Spalten einfrieren hat ' + durchEinfrieren + ' Elemente in der Höhe verändert');
  if (durchFixierung) bericht.fehler.push('Silbentrennung hat ' + durchFixierung + ' Elemente in der Höhe verändert (Satz verschoben)');

  /* Prüfung: Überlauf, Grenzschnitte, Füllstand */
  seiten.forEach((p, i) => {
    const k = p.querySelector('.koerper');
    const kb = k.getBoundingClientRect();
    const spalten = p.classList.contains('spalten');
    let unten = kb.top, rechts = kb.left;
    for (const c of k.children) for (const r of c.getClientRects()) { unten = Math.max(unten, r.bottom); rechts = Math.max(rechts, r.right); }
    const fuell = (unten - kb.top) / kb.height;
    const ueber = unten > kb.bottom + TOL || rechts > kb.right + TOL;
    let schnitte = 0;
    p.querySelectorAll('.unit').forEach(u => {
      for (const r of u.getClientRects()) if (r.bottom > kb.bottom + TOL || r.top < kb.top - TOL || r.right > kb.right + TOL) { schnitte++; break; }
    });
    /* Lage des Satzspiegels selbst prüfen: Er muss exakt im Seitenrand sitzen. Eine Verschiebung
       (etwa durch zusammenfallende Abstände) verschiebt sonst den Maßstab aller übrigen Prüfungen. */
    if (!p.classList.contains('deck')) {
      const pr = p.getBoundingClientRect(), cs = getComputedStyle(p);
      const dOben = kb.top - (pr.top + parseFloat(cs.paddingTop)), dUnten = (pr.bottom - parseFloat(cs.paddingBottom)) - kb.bottom;
      if (Math.abs(dOben) > TOL || Math.abs(dUnten) > TOL)
        bericht.fehler.push('Seite ' + (i + 1) + ': Satzspiegel verschoben (oben ' + (dOben / 3.78).toFixed(1) + ' mm, unten ' + (dUnten / 3.78).toFixed(1) + ' mm)');
    }
    /* Auch frei positionierte Elemente (etwa das Impressum) müssen im Satzspiegel und auf dem Blatt liegen. */
    const blatt = p.getBoundingClientRect();
    let frei = 0;
    k.querySelectorAll('*').forEach(e => {
      const st = getComputedStyle(e).position;
      if (st !== 'absolute' && st !== 'fixed') return;
      const r = e.getBoundingClientRect();
      if (r.height && (r.bottom > kb.bottom + TOL || r.bottom > blatt.bottom - TOL)) frei++;
    });
    if (frei) bericht.fehler.push('Seite ' + (i + 1) + ': ' + frei + ' frei positionierte(s) Element(e) außerhalb des Satzspiegels');
    /* Titelseite: Textblöcke dürfen einander nicht überlagern (Titel, Register, Fuß). */
    if (p.classList.contains('deck')) {
      const bloecke = [p.querySelector('.tp-band'), p.querySelector('.tp-mitte'), p.querySelector('.tp-fuss'),
                       ...p.querySelectorAll('.daumen em')].filter(Boolean).map(e => e.getBoundingClientRect());
      const schneidet = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
      let n = 0;
      for (let x = 0; x < bloecke.length; x++) for (let y = x + 1; y < bloecke.length; y++) if (schneidet(bloecke[x], bloecke[y])) n++;
      if (n) bericht.fehler.push('Titelseite: ' + n + ' Überlappung(en) von Textblöcken');
    }
    const nurKopf = k.children.length === 1 && k.querySelector('.provkopf') && !k.querySelector('.kachel');
    const a = ['deck', 'titelei', 'spalten', 'quer'].find(x => p.classList.contains(x)) || 'normal';
    const erste = k.querySelector('.unit');
    bericht.seiten.push({ nr: i + 1, art: a, zwang: !!(erste && erste.dataset.neueSeite === '1'), fuellstand: +Math.min(fuell, 9.99).toFixed(3),
      einheiten: p.querySelectorAll('.unit').length, ueberlauf: ueber, schnitte });
    if (ueber) bericht.fehler.push('Seite ' + (i + 1) + ': Überlauf');
    /* 3.6: Überstand nach rechts. Ragt irgendetwas über die Seitenbreite, verkleinert Chromium beim Drucken
       ALLE Seiten (breiter weißer Rand unten und rechts). scrollWidth berücksichtigt abgeschnittene Bereiche
       (Wasserzeichen, SVG) korrekt. */
    if (p.scrollWidth > p.clientWidth + 1)
      bericht.fehler.push('Seite ' + (i + 1) + ': Inhalt ragt ' + ((p.scrollWidth - p.clientWidth) / 3.78).toFixed(1) +
                          ' mm über den rechten Seitenrand (Chromium verkleinert sonst alle Seiten)');
    if (schnitte) bericht.fehler.push('Seite ' + (i + 1) + ': ' + schnitte + ' Einheit(en) über der Satzspiegelgrenze');
    if (nurKopf) bericht.warnungen.push('Seite ' + (i + 1) + ': Provinzkopf allein auf der Seite');
  });
  /* Kennzahlen des Umbruchs (3.6): Fortsetzungen, Kleinreste, Anrisse, Leerraum, Abbildungen */
  const U = bericht.umbruch, KLEIN = 0.20;
  U.fortsetzungen = 0; U.fortsetzungen_ein_baustein = 0; U.kleinreste = []; U.anrisse = []; U.leerraum = []; U.abbildungen = [];
  seiten.forEach((p, i) => {
    const k = p.querySelector('.koerper'), kb = k.getBoundingClientRect();
    const a = ['deck', 'titelei', 'spalten', 'quer'].find(x => p.classList.contains(x)) || 'normal';
    if (a === 'normal' || a === 'quer') U.leerraum.push([i + 1, +Math.max(0, 1 - bericht.seiten[i].fuellstand).toFixed(3)]);
    k.querySelectorAll(':scope > .kachel').forEach(t => {
      const h = t.getBoundingClientRect().height / kb.height;
      const fort = t.classList.contains('fortsetzung'), offen = t.classList.contains('offen-unten');
      if (fort) { U.fortsetzungen++; if (t.querySelectorAll(':scope > .unit').length === 1) U.fortsetzungen_ein_baustein++; }
      const eins = t.querySelectorAll(':scope > .unit').length === 1;  /* Kleinrest, Anriss: ein einzelner kleiner Baustein */
      if (fort && !offen && eins && h < KLEIN) U.kleinreste.push(t.dataset.code + ' S ' + (i + 1));
      if (!fort && offen && eins && h < KLEIN) U.anrisse.push(t.dataset.code + ' S ' + (i + 1));
    });
    p.querySelectorAll('.fig').forEach(f => {
      const pt = kleinsteSchrift(f), kc = f.closest('.unit');
      U.abbildungen.push({ abb: f.dataset.abb ? +f.dataset.abb : null, kachel: kc ? (kc.dataset.kachel || kc.dataset.name || null) : null, seite: i + 1,
        skala: f.dataset.skala ? +f.dataset.skala : 1, art: f.dataset.stufenart || (f.classList.contains('atmend') ? 'hoehe' : 'skala'),
        min_pt: pt === null ? null : +pt.toFixed(2) });
    });
  });
  U.abbildungen.forEach(f => {
    if (f.art === 'skala' && f.skala < 0.999 && f.min_pt !== null && f.min_pt < MIN_PT - 0.01)
      bericht.warnungen.push('Abbildung in ' + f.kachel + ': kleinste Grafikschrift ' + f.min_pt.toFixed(1).replace('.', ',') + ' pt nach Verkleinern (Mindestmaß 6,5 pt)');
    else if (f.min_pt !== null && f.min_pt < MIN_PT - 0.01)
      bericht.hinweise.push('Abbildung in ' + f.kachel + ': Grafikschrift schon unverkleinert ' + f.min_pt.toFixed(1).replace('.', ',') + ' pt (unter 6,5 pt; Grafik im Werk vergrößern)');
  });
  if (U.kleinreste.length) bericht.warnungen.push('Kleinrest (Fortsetzung aus einem Baustein unter 20 % der Seite): ' + U.kleinreste.join(', '));
  if (U.anrisse.length) bericht.warnungen.push('Anriss (Kachelanfang aus einem Baustein unter 20 % am Seitenende): ' + U.anrisse.join(', '));
  /* Kacheln höher als eine Seite teilt jedes Verfahren; Hinweis an den Autor */
  for (const st of S) {
    if (!st.M) continue;
    const hoehe = new Map();
    st.M.einheiten.forEach((e, j) => {
      if (!e.key) return;
      const weiter = st.M.einheiten[j + 1] && st.M.einheiten[j + 1].key === e.key;
      hoehe.set(e.key, (hoehe.has(e.key) ? hoehe.get(e.key) : e.oben + e.unten) + e.h[e.h.length - 1] + (weiter ? e.gapNach : 0));
    });
    hoehe.forEach((h, code) => { if (h > st.M.C) bericht.hinweise.push('Kachel ' + code + ' ist höher als eine Seite (' + Math.round(h / st.M.C * 100) + ' %); sie wird stets geteilt'); });
  }
  window.__bericht = bericht;
  window.__fertig = true;
})();
