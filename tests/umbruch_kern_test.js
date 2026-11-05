/* (c) Oliver Bedernik · Terra-Kit · tests/umbruch_kern_test.js
   Rechenkern des globalen Umbruchs ohne Browser (3.6). Aufruf: node tests/umbruch_kern_test.js
   Gibt „ok“ aus oder die erste verletzte Bedingung (Exitcode 1). */
const path = require('path');
const U = require(path.join(__dirname, '..', 'vorlage', 'umbruch.js'));

const e = (key, h, gap, extra) => Object.assign({ key, h: [h], strafe: [0], tab: null, oben: 2, unten: 2, gapNach: gap, kopf: false }, extra || {});
const fehler = [];
const pruefe = (bed, text) => { if (!bed) fehler.push(text); };

/* 1. Gierig entstünde ein Kleinrest (X3 allein auf Seite 2); der Plan vermeidet ihn. */
const m1 = { C: 100, of: 3, minZeilen: 3, startFort: false,
  einheiten: [e('X', 45, 1), e('X', 45, 1), e('X', 8, 2), e('Y', 50, 0)] };
const p1 = U.plane(m1);
pruefe(U.kennzahlen(p1).kleinreste === 0, 'Kleinrest nicht vermieden');
pruefe(JSON.stringify(U.plane(m1)) === JSON.stringify(p1), 'Plan nicht deterministisch');

/* 2. Abbildungsstufe: 5 px fehlen; gewählt wird die mildeste Stufe, die reicht. */
const m2 = { C: 100, of: 3, minZeilen: 3, startFort: false,
  einheiten: [e('A', 39, 1), e('A', 60, 0, { h: [60, 54, 48], strafe: [0, 1, 2] })] };
const p2 = U.plane(m2);
pruefe(p2.seiten.length === 1 && JSON.stringify(p2.seiten[0].wahl) === '[[1,1]]', 'Abbildungsstufe nicht minimal: ' + JSON.stringify(p2.seiten.map(s => s.wahl)));

/* 3. Tabellen: Bruch nur nach mindestens drei Zeilen und vor mindestens drei Zeilen. */
const zeilen = new Array(30).fill(6);
const m3 = { C: 100, of: 3, minZeilen: 3, startFort: false,
  einheiten: [e('T', 0, 0, { tab: { hf0: 10, hc0: 8, hw: 3, delta: 0, zeilen } })] };
const p3 = U.plane(m3);
const teile = p3.seiten.map(s => s.e - s.s);
pruefe(teile.every(n => n >= 3) && teile.reduce((a, b) => a + b, 0) === 30, 'Tabellenteile verletzen die Mindestzeilen: ' + teile);

/* 4. Ausschluss einer Seite (Korrektur nach Messabweichung) wird beachtet; eine Seite aus nur einem
      Bruchintervall kann nicht ausgeschlossen werden (es gibt nichts Kleineres). */
const mehr = p3.seiten.find(s => s.e - s.s > 3);
const p4 = U.plane(m3, null, { start: mehr.s, verboten: new Set([mehr.s + ',' + mehr.e]) });
pruefe(p4.seiten.length && p4.seiten[0].s === mehr.s && p4.seiten[0].e !== mehr.e, 'verbotene Seite erneut geplant');

/* 5. Bindungen (3.7): vor Kästen schwach, Formel vor Rechenweg stark. */
pruefe(U.bindung({ bs: 'kern' }, { bs: 'merke' }) === 0.5 && U.bindung({ bs: 'formel' }, { bs: 'rechenweg' }) === 2
       && U.bindung({ bs: 'kern' }, { bs: 'schema' }) === 1, 'Bindungen falsch');

console.log(fehler.length ? fehler[0] : 'ok');
process.exit(fehler.length ? 1 : 0);
