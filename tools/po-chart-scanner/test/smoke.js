// Arnes de prueba: carga los modulos de analisis del PO Chart Scanner
// en Node con stubs minimos de window/document/localStorage y ejecuta
// el pipeline de scoring sobre velas sinteticas.
const fs = require('fs'), vm = require('vm'), path = require('path');
const BASE = process.argv[2];

const store = {};
const sandbox = {
  console: Object.assign(Object.create(console), { table: () => {} }),
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; }
  },
  document: { querySelector: () => null },
  Date, Math, JSON, Object, Array, String, Number, isFinite, parseInt, parseFloat
};
sandbox.window = sandbox;
sandbox.window.addEventListener = () => {};
vm.createContext(sandbox);

const MODS = ['config','indicators','patternDetector','supportResistance',
  'trendAnalyzer','candleArchive','trapDetector','orderFlowDetector',
  'crowdBehavior','contrarianScoring','scoring','history','panel'];
for (const m of MODS) {
  const p = path.join(BASE, 'src', m + '.js');
  vm.runInContext(fs.readFileSync(p, 'utf8'), sandbox, { filename: m + '.js' });
}
const P = sandbox.POScannerPRO;
console.log('Modulos cargados:', P._mods.join(', '));

// --- Generador de velas en espacio-Y del lector (Y menor = precio mayor) ---
function serie(n, fn) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const mid = fn(i);
    const body = 6 + (i % 3) * 2;
    const up = (i % 4) * 2, dn = (i % 5) * 2;
    const alcista = fn(i + 1) < mid;            // el precio sube -> Y baja
    const bodyTop = mid - body / 2, bodyBottom = mid + body / 2;
    out.push({
      x: i * 6, width: 4, dir: alcista ? 'CALL' : 'PUT',
      high: bodyTop - up, low: bodyBottom + dn,
      open: alcista ? bodyBottom : bodyTop,
      close: alcista ? bodyTop : bodyBottom,
      bodyTop, bodyBottom, bodySize: body, wickUp: up, wickDown: dn
    });
  }
  return out;
}

const casos = {
  'TENDENCIA ALCISTA (precio sube: Y baja)':   serie(80, i => 400 - i * 2),
  'TENDENCIA BAJISTA (precio baja: Y sube)':   serie(80, i => 200 + i * 2),
  'RANGO LATERAL (oscila en canal)':           serie(80, i => 300 + Math.sin(i / 4) * 25),
  'CAIDA + GIRO FINAL (reversion alcista)':    serie(80, i => i < 60 ? 200 + i * 2 : 320 - (i - 60) * 4)
};

let fallos = 0;
for (const [nombre, velas] of Object.entries(casos)) {
  const r = P.Scoring.evaluate(velas, { asset: 'EUR/USD OTC', tfSec: 60 });
  const d = r.detail;
  console.log('\n--- ' + nombre + ' ---');
  console.log('  dir=' + r.dir + '  score=' + r.score + '  raw=' + r.rawScore +
              '  calidad=' + r.quality + '  confirmada=' + r.confirmed +
              '  bloqueada=' + r.blocked + (r.blockReason ? '(' + r.blockReason + ')' : ''));
  console.log('  tendencia=' + d.trend + '/' + d.trendStrength + '  RSI=' + d.rsi +
              '  confluencia=' + d.confluencia + '  S/R=' + d.srNear + ' x' + d.srLevels);
  if (r.contraNote) console.log('  contraNote: ' + r.contraNote);
  if (r.warning) console.log('  warning: ' + r.warning.slice(0, 110));
  console.log('  trapIndex=' + d.trapIndex + '%  reversalRatio=' + d.reversalRatio +
              '  fakeout=' + d.fakeout + '  actividad=' + d.actividad +
              '  contrarian=' + r.contrarian + '  obvia=' + r.esObvia);
  // Invariantes que deben cumplirse SIEMPRE
  const inv = [
    ['score en 0..100', r.score >= 0 && r.score <= 100],
    ['score numerico', Number.isFinite(r.score)],
    ['dir valido', r.dir === 'CALL' || r.dir === 'PUT'],
    ['score <= rawScore + bonus contrarian', r.score <= r.rawScore + P.CONFIG.CONTRARIAN.FAKEOUT_BONUS],
    // el techo estructural solo BAJA; un bloqueo por confluencia no techa,
    // asi que ahi el score si puede superar rawScore (bonus contrarian)
    ['bonus por encima del techo SOLO si es contrarian', r.score <= r.rawScore || r.contrarian],
    ['trapIndex 0..100', d.trapIndex >= 0 && d.trapIndex <= 100],
    ['bloqueo estructural nunca sube el score',
      !(r.blocked && r.blockReason === 'estructura' && r.score > r.rawScore)],
    // v4.3.1: los avisos contrarian van en contraNote, NUNCA en warning
    // (el panel pinta warning como "CONTRA-ESTRUCTURA - Riesgo Alto")
    ['warning limpio de avisos contrarian',
      !r.warning || !/CONTRARIAN|Trap Index|MASA OBVIA|Order flow/.test(r.warning)],
    ['senal contrarian NO se marca contra-estructura', !(r.contrarian && r.warning)],
    // v4.3.1: una senal ya bloqueada no recibe castigos contrarian encima
    ['bloqueada => sin castigo contrarian doble',
      !r.blocked || !r.contraNote || !/pts$|BLOQUEADO: MASA/.test(r.contraNote)]
  ];
  inv.forEach(([k, ok]) => { if (!ok) { console.log('  !! INVARIANTE ROTA: ' + k); fallos++; } });
}

// --- Direccionalidad: tendencia clara debe dar la direccion correcta ---
const alza = P.Scoring.evaluate(casos['TENDENCIA ALCISTA (precio sube: Y baja)'], {});
const baja = P.Scoring.evaluate(casos['TENDENCIA BAJISTA (precio baja: Y sube)'], {});
console.log('\n=== DIRECCIONALIDAD ===');
console.log('  alcista -> ' + alza.dir + (alza.dir === 'CALL' ? ' OK' : ' INCORRECTO'));
console.log('  bajista -> ' + baja.dir + (baja.dir === 'PUT' ? ' OK' : ' INCORRECTO'));
if (alza.dir !== 'CALL') fallos++;
if (baja.dir !== 'PUT') fallos++;

// --- Archivo de velas + backtest + historial ---
console.log('\n=== ARCHIVO / BACKTEST / HISTORIAL ===');
const n1 = P.CandleArchive.add('EUR/USD OTC', 60, casos['RANGO LATERAL (oscila en canal)']);
const n2 = P.CandleArchive.add('EUR/USD OTC', 60, casos['RANGO LATERAL (oscila en canal)']);
console.log('  archivo tras 2 escaneos identicos: ' + n1 + ' -> ' + n2 + ' velas (dedup por rejilla)');
if (n2 !== n1) { console.log('  !! el dedup no funciono'); fallos++; }
console.log('  backtest:', JSON.stringify(P.CandleArchive.backtest('EUR/USD OTC', 60, 1)));
console.log('  MTF sintetico:', JSON.stringify(P.CandleArchive.higherTrend('EUR/USD OTC', 60)));

P.History.add({ asset: 'EUR/USD OTC', dir: 'CALL', score: 80, quality: 'MEDIUM',
  refPrice: 1.1000, refReal: true, refT: Date.now() - 61000, tfSec: 60,
  deadline: Date.now() - 1000, expiryText: '1m', tag: 'CONTRARIAN' });
P.History.update(1.1005);   // el precio SUBIO -> CALL debe ganar
const st = P.History.stats();
console.log('  historial:', JSON.stringify(st), 'byTag CONTRARIAN:',
  JSON.stringify(P.History.byTag('CONTRARIAN')));
if (st.wins !== 1) { console.log('  !! el WIN/LOSS con precio real no se evaluo bien'); fallos++; }

// ============================================================
// v4.4: umbral de confluencia, etiquetas de accion, setup perfecto
// ============================================================
console.log('\n=== v4.4 UMBRAL DE CONFLUENCIA ===');
const F = P.CONFIG.FILTER;
for (const [nombre, velas] of Object.entries(casos)) {
  const r = P.Scoring.evaluate(velas, {});
  const need = r.perfecto ? F.MIN_CONFLUENCIA_PERFECTO : F.MIN_CONFLUENCIA;
  const conf = parseInt(r.detail.confluencia, 10);
  const debeBloquear = conf < need;
  const ok = debeBloquear ? r.blocked : true;   // por debajo del umbral -> bloqueada
  console.log('  ' + nombre.slice(0, 34).padEnd(34) +
    ' conf=' + r.detail.confluencia + ' need=' + need +
    ' blocked=' + r.blocked + (r.blockReason ? '(' + r.blockReason + ')' : '') +
    (ok ? '  OK' : '  FALLO'));
  if (!ok) fallos++;
}

console.log('\n=== v4.4 ETIQUETAS DE ACCION ===');
const esperado = [
  [95, false, false, 'OPERAR'],
  [90, false, false, 'OPERAR'],
  [89, false, false, 'OPERAR SI CONTRARIAN'],
  [87, true,  false, 'OPERAR (CONTRARIAN)'],
  [84, false, false, 'RIESGO MEDIO'],
  [75, false, false, 'RIESGO MEDIO'],
  [74, false, false, 'NO OPERAR'],
  [60, false, false, 'NO OPERAR'],
  [59, false, false, 'NO OPERAR - SCORE BAJO'],
  [95, false, true,  'BLOQUEADA - NO OPERAR']   // bloqueada manda sobre el score
];
esperado.forEach(([score, contrarian, blocked, txt]) => {
  const a = P.Panel.actionLabel({ score, contrarian, blocked });
  const ok = a.text === txt;
  console.log('  score ' + String(score).padStart(3) +
    (blocked ? ' bloqueada' : contrarian ? ' contrarian' : '          ') +
    ' -> ' + a.text.padEnd(24) + '[' + a.cls + ']' + (ok ? ' OK' : ' FALLO: esperaba ' + txt));
  if (!ok) fallos++;
});

console.log('\n=== v4.4 SETUP CONTRARIAN PERFECTO ===');
// Sin muestra de senales CONTRARIAN el backtest NO se da por
// cumplido: la condicion debe faltar y decirlo, no inventarse.
const sinMuestra = P.ContrarianScoring.adjust({
  dir: 'PUT', score: 80, agree: 9, candles: casos['RANGO LATERAL (oscila en canal)'],
  trend: { trend: 'FLAT', strength: 0 },
  sr: P.SupportResistance.proximity(casos['RANGO LATERAL (oscila en canal)']),
  patterns: [], blocked: false
});
const pideBacktest = sinMuestra.faltanPerfecto.some(f => /backtest/.test(f));
console.log('  sin muestra -> perfecto=' + sinMuestra.perfecto +
  ' | falta: ' + sinMuestra.faltanPerfecto.join(', '));
if (sinMuestra.perfecto) { console.log('  !! marco PERFECTO sin muestra de backtest'); fallos++; }
if (!pideBacktest) { console.log('  !! no reporta la condicion de backtest como faltante'); fallos++; }

// Con REQUIRE_BACKTEST desactivado, un setup que cumple el resto
// SI debe llegar a 90+ con el bonus.
P.CONFIG.PERFECT.REQUIRE_BACKTEST = false;
const velasFk = casos['CAIDA + GIRO FINAL (reversion alcista)'];
const srFk = P.SupportResistance.proximity(velasFk);
const conBonus = P.ContrarianScoring.adjust({
  dir: 'PUT', score: 80, agree: 9, candles: velasFk,
  trend: { trend: 'FLAT', strength: 0 }, sr: srFk, patterns: [], blocked: false
});
console.log('  sin exigir backtest -> perfecto=' + conBonus.perfecto +
  ' score 80 -> ' + conBonus.score + ' | falta: ' +
  (conBonus.faltanPerfecto.join(', ') || 'nada'));
if (conBonus.perfecto && conBonus.score < P.CONFIG.PERFECT.MIN_SCORE) {
  console.log('  !! perfecto pero no llego al piso de 90'); fallos++;
}
if (!conBonus.perfecto && !conBonus.faltanPerfecto.length) {
  console.log('  !! no perfecto pero no dice que falta'); fallos++;
}
P.CONFIG.PERFECT.REQUIRE_BACKTEST = true;

console.log('\n=== v4.4 BACKTEST SEPARADO ===');
P.History.add({ asset: 'X', dir: 'PUT', score: 70, quality: 'MEDIUM',
  refPrice: 2, refReal: true, refT: Date.now() - 61000, tfSec: 60,
  deadline: Date.now() - 1000, tag: 'NORMAL' });
P.History.update(3);                    // subio -> PUT pierde
const bts = P.History.backtests();
console.log('  ' + JSON.stringify(bts));
if (bts.contrarian.n !== 1 || bts.normal.n !== 1 || bts.total.n !== 2) {
  console.log('  !! las tres categorias no cuadran'); fallos++;
}
if (bts.total.acc !== 50) { console.log('  !! total deberia ser 50%'); fallos++; }

// ============================================================
// v4.4.1: seleccion del PRECIO REAL del eje (DOM simulado).
// Es la fuente de verdad del WIN/LOSS: si falla, el historial
// cae a comparar pixeles del archivo y las estadisticas mienten.
// ============================================================
console.log('\n=== v4.4.1 PRECIO REAL DEL EJE ===');
const TRANSP = 'rgba(0, 0, 0, 0)';
function nodo(o) {
  const n = {
    textContent: o.text,
    children: o.hijos || [],
    _bg: o.bg || TRANSP,
    parentElement: null,
    getBoundingClientRect: () => ({ left: o.x, top: o.y || 100,
                                    width: o.w == null ? 60 : o.w, height: 14 }),
    closest: sel => (sel === '#po-pro-panel' && o.enPanel) ? {} : null
  };
  if (o.bgPadre) {                       // fondo pintado en el padre
    n.parentElement = { _bg: o.bgPadre, parentElement: null,
                        children: [n], getBoundingClientRect: n.getBoundingClientRect,
                        closest: () => null };
  }
  return n;
}
function conDom(nodos, fn) {
  const docPrev = sandbox.document, gcsPrev = sandbox.getComputedStyle,
        iwPrev = sandbox.innerWidth, ihPrev = sandbox.innerHeight;
  sandbox.document = { querySelectorAll: () => nodos, querySelector: () => null };
  sandbox.getComputedStyle = n => ({ backgroundColor: (n && n._bg) || TRANSP });
  sandbox.innerWidth = 1900;
  sandbox.innerHeight = 900;
  try { return fn(); }
  finally { sandbox.document = docPrev; sandbox.getComputedStyle = gcsPrev;
           sandbox.innerWidth = iwPrev; sandbox.innerHeight = ihPrev; }
}

const pruebasPrecio = [
  ['etiqueta resaltada vs etiqueta fija del eje',
    [nodo({ text: '0.55465', x: 1640, bg: 'rgb(46, 125, 90)' }),
     nodo({ text: '0.55500', x: 1700 })],                      // fija, sin fondo
    0.55465],
  ['fondo pintado en el PADRE (pildora de PO)',
    [nodo({ text: '1.23456', x: 1650, bgPadre: 'rgb(20, 30, 40)' })],
    1.23456],
  ['digito animado en un span hijo',
    [nodo({ text: '0.98765', x: 1660, hijos: [{}], bg: 'rgb(9, 9, 9)' })],
    0.98765],
  ['dos resaltadas: gana la mas a la derecha (el eje)',
    [nodo({ text: '1.11111', x: 1200, bg: 'rgb(1, 1, 1)' }),
     nodo({ text: '2.22222', x: 1680, bg: 'rgb(2, 2, 2)' })],
    2.22222],
  ['sin fondo pintado -> null (mejor que un precio fijo)',
    [nodo({ text: '0.55465', x: 1640 })],
    null],
  ['fuera de la banda derecha -> null',
    [nodo({ text: '0.55465', x: 200, bg: 'rgb(1, 1, 1)' })],
    null],
  ['dentro de nuestro panel -> ignorado',
    [nodo({ text: '0.55465', x: 1640, bg: 'rgb(1, 1, 1)', enPanel: true })],
    null],
  ['coma decimal',
    [nodo({ text: '1,23456', x: 1650, bg: 'rgb(1, 1, 1)' })],
    1.23456],
  ['nada que parezca precio -> null', [], null]
];
pruebasPrecio.forEach(([nombre, nodos, esperado]) => {
  const got = conDom(nodos, () => P.Panel.findCurrentPrice());
  const ok = got === esperado;
  console.log('  ' + nombre.padEnd(46) + ' -> ' + String(got).padEnd(9) +
    (ok ? 'OK' : 'FALLO: esperaba ' + esperado));
  if (!ok) fallos++;
});
// El diagnostico debe contar bien lo que hay
const d = conDom(
  [nodo({ text: '0.55465', x: 1640, bg: 'rgb(1, 1, 1)' }),
   nodo({ text: '0.55500', x: 1700 }),
   nodo({ text: '9.99999', x: 100, bg: 'rgb(1, 1, 1)' })],
  () => P.Panel.diagPrice());
const dOk = d.total === 3 && d.enBanda === 2 && d.conFondo === 1;
console.log('  diagPrice cuenta total/enBanda/conFondo'.padEnd(48) + '-> ' +
  d.total + '/' + d.enBanda + '/' + d.conFondo + '  ' + (dOk ? 'OK' : 'FALLO'));
if (!dOk) fallos++;

// ============================================================
// v4.4.2: METODO 2 - calibrar la escala del eje y traducir
// pixeles a precio real. Es el fallback cuando la etiqueta
// resaltada no aparece.
// ============================================================
console.log('\n=== v4.4.2 CALIBRACION DE LA ESCALA DEL EJE ===');
// Eje sintetico: 3 etiquetas fijas, 100 px = 0.0010 de precio.
// (en pantalla, bajar de Y = bajar de precio)
const ejeOk = [nodo({ text: '0.55600', x: 1700, y: 100 }),
               nodo({ text: '0.55500', x: 1700, y: 200 }),
               nodo({ text: '0.55400', x: 1700, y: 300 })];
const esc = conDom(ejeOk, () => P.Panel.axisScale());
console.log('  escala: n=' + (esc && esc.n) + ' R2=' + (esc && esc.r2.toFixed(5)));
if (!esc || esc.n !== 3 || esc.r2 < 0.995) { console.log('  !! no calibro'); fallos++; }

const pruebasY = [[107, 0.556], [207, 0.555], [307, 0.554], [157, 0.5555]];
pruebasY.forEach(([y, esperado]) => {
  const got = conDom(ejeOk, () => P.Panel.priceFromY(y));
  const ok = got != null && Math.abs(got - esperado) < 1e-6;
  console.log('  y=' + String(y).padStart(3) + ' -> ' + String(got).padEnd(9) +
    (ok ? 'OK' : 'FALLO: esperaba ' + esperado));
  if (!ok) fallos++;
});

// Traducir la ultima vela leida (coords de imagen -> viewport -> precio)
const velaTest = { close: 200 };                 // y de imagen
const convTest = { left: 0, top: 7, sx: 1, sy: 1 };  // viewport = 7 + 200 = 207
const pv = conDom(ejeOk, () => P.Panel.priceFromCandle(velaTest, convTest));
console.log('  vela (close y=200, conv top=7) -> ' + pv +
  (Math.abs(pv - 0.555) < 1e-6 ? '  OK' : '  FALLO'));
if (!(Math.abs(pv - 0.555) < 1e-6)) fallos++;

// Un eje mal leido NO debe producir un numero inventado
const ejeMalo = [nodo({ text: '0.55600', x: 1700, y: 100 }),
                 nodo({ text: '0.55500', x: 1700, y: 200 }),
                 nodo({ text: '0.99999', x: 1700, y: 210 })];  // fuera de recta
const escMala = conDom(ejeMalo, () => P.Panel.axisScale());
console.log('  eje incoherente -> ' + (escMala ? 'CALIBRO (FALLO)' : 'null  OK'));
if (escMala) fallos++;
// Pendiente positiva (precio sube con Y) = eje invertido: rechazar
const ejeInv = [nodo({ text: '0.55400', x: 1700, y: 100 }),
                nodo({ text: '0.55500', x: 1700, y: 200 }),
                nodo({ text: '0.55600', x: 1700, y: 300 })];
const escInv = conDom(ejeInv, () => P.Panel.axisScale());
console.log('  eje invertido   -> ' + (escInv ? 'CALIBRO (FALLO)' : 'null  OK'));
if (escInv) fallos++;

console.log('\n=== v4.4.2 UMBRAL 6/12 Y BACKTEST RELAJADO ===');
console.log('  MIN_CONFLUENCIA=' + P.CONFIG.FILTER.MIN_CONFLUENCIA +
            ' perfecto=' + P.CONFIG.FILTER.MIN_CONFLUENCIA_PERFECTO +
            ' | backtest min ' + P.CONFIG.PERFECT.BACKTEST_MIN_ACC +
            '% con muestra ' + P.CONFIG.PERFECT.BACKTEST_MIN_N);
if (P.CONFIG.FILTER.MIN_CONFLUENCIA !== 6) { console.log('  !! umbral no es 6'); fallos++; }
let desbloqueadas6 = 0;
for (const [nombre, velas] of Object.entries(casos)) {
  const r = P.Scoring.evaluate(velas, {});
  const conf = parseInt(r.detail.confluencia, 10);
  if (conf === 6 && r.blockReason !== 'confluencia') desbloqueadas6++;
  console.log('  ' + nombre.slice(0, 34).padEnd(34) + ' conf=' + r.detail.confluencia +
    ' blocked=' + r.blocked + (r.blockReason ? '(' + r.blockReason + ')' : ''));
}
console.log('  senales de 6/12 ya NO bloqueadas por confluencia: ' + desbloqueadas6);
if (!desbloqueadas6) { console.log('  !! ninguna 6/12 se desbloqueo'); fallos++; }

// Con muestra de 5 contrarian ganadoras, un setup perfecto llega a 90+
P.History.clear();
for (let i = 0; i < 5; i++) {
  P.History.add({ asset: 'A' + i, dir: 'PUT', score: 80, quality: 'MEDIUM',
    refPrice: 2, refReal: true, refT: Date.now() - 61000, tfSec: 60,
    deadline: Date.now() - 1000, tag: 'CONTRARIAN', refMethod: 'eje' });
  P.History.update(1);            // bajo -> PUT gana
}
const bt5 = P.History.byTag('CONTRARIAN');
const velasFk2 = casos['CAIDA + GIRO FINAL (reversion alcista)'];
const perf = P.ContrarianScoring.adjust({
  dir: 'PUT', score: 80, agree: 9, candles: velasFk2,
  trend: { trend: 'FLAT', strength: 0 },
  sr: P.SupportResistance.proximity(velasFk2), patterns: [], blocked: false });
console.log('  muestra contrarian: ' + bt5.acc + '% en ' + bt5.n +
  ' -> perfecto=' + perf.perfecto + ' score 80 -> ' + perf.score +
  ' | falta: ' + (perf.faltanPerfecto.join(', ') || 'nada'));
if (perf.perfecto && perf.score < 90) { console.log('  !! perfecto sin llegar a 90'); fallos++; }

// Setup contrarian PERFECTO completo: nivel x4 + fakeout a favor
// + confluencia 9 + trap bajo + muestra de backtest -> debe llegar a 90+
const NIVEL = 250;                       // resistencia en pixel Y
const velasPerf = [];
for (let i = 0; i < 60; i++) {           // velas limpias, mechas cortas
  velasPerf.push({ x: i * 6, width: 4, dir: i % 2 ? 'CALL' : 'PUT',
    high: 294, low: 306, open: 295, close: 305,
    bodyTop: 295, bodyBottom: 305, bodySize: 10, wickUp: 1, wickDown: 1 });
}
// ultima vela: la mecha PINCHA por encima de la resistencia (high 240 < 250)
// pero el cierre vuelve por debajo (260 > 250) = ruptura falsa alcista
velasPerf.push({ x: 366, width: 4, dir: 'CALL',
  high: 240, low: 275, open: 270, close: 260,
  bodyTop: 260, bodyBottom: 270, bodySize: 10, wickUp: 20, wickDown: 5 });
const srPerf = { near: { y: NIVEL, type: 'R', touches: 4 },
                 levels: [{ y: NIVEL, type: 'R', touches: 4 }] };
const perfOk = P.ContrarianScoring.adjust({
  dir: 'PUT', score: 80, agree: 9, candles: velasPerf,
  trend: { trend: 'FLAT', strength: 0 }, sr: srPerf,
  patterns: [], blocked: false });
console.log('  SETUP PERFECTO COMPLETO -> perfecto=' + perfOk.perfecto +
  ' | trap=' + perfOk.trapIndex + '% | fakeout=' + perfOk.fakeout +
  ' | score 80 -> ' + perfOk.score +
  (perfOk.faltanPerfecto.length ? ' | falta: ' + perfOk.faltanPerfecto.join(', ') : ''));
if (!perfOk.perfecto) { console.log('  !! no lo marco como PERFECTO'); fallos++; }
if (perfOk.score < 90) { console.log('  !! no llego a 90+'); fallos++; }
if (!perfOk.contrarian) { console.log('  !! no lo marco CONTRARIAN'); fallos++; }

console.log('\n=== v4.4.3 TIMEFRAME ANCLADO AL CHIP ===');
// Reproduce la pantalla del usuario: chip S10 activo arriba a la
// izquierda, y la palabra M30 suelta en un menu a la derecha.
function chip(o) {
  const n = nodo(o);
  n.getBoundingClientRect = () => ({ left: o.x, top: o.y,
                                     width: o.w || 30, height: o.h || 18 });
  return n;
}
const pruebasTf = [
  ['chip S10 activo vs M30 en un menu lejano',
    [chip({ text: 'S10', x: 250, y: 140, bg: 'rgb(30, 90, 200)' }),
     chip({ text: 'M30', x: 1500, y: 300 })],
    'S10'],
  ['sin fondo: gana el chip mas pequeno de la zona del grafico',
    [chip({ text: 'M1', x: 250, y: 140, w: 24, h: 16 }),
     chip({ text: 'H4', x: 300, y: 140, w: 90, h: 40 })],
    'M1'],
  ['elemento grande no es un chip',
    [chip({ text: 'M30', x: 250, y: 140, w: 200, h: 60 })],
    null],
  ['fuera de la zona del grafico (derecha) se ignora',
    [chip({ text: 'M30', x: 1500, y: 140, bg: 'rgb(1,1,1)' })],
    null],
  ['fuera de la zona del grafico (abajo) se ignora',
    [chip({ text: 'M30', x: 250, y: 700, bg: 'rgb(1,1,1)' })],
    null]
];
pruebasTf.forEach(([nombre, nodos, esperado]) => {
  const got = conDom(nodos, () => P.Panel.findTimeframe());
  const ok = got === esperado;
  console.log('  ' + nombre.padEnd(48) + '-> ' + String(got).padEnd(6) +
    (ok ? 'OK' : 'FALLO: esperaba ' + esperado));
  if (!ok) fallos++;
});
// Los timeframes cortos de PO deben existir en la tabla
['S10', 'S15', 'S30', 'M1', 'M2', 'H2'].forEach(k => {
  if (!P.CONFIG.TF_SECONDS[k]) { console.log('  !! falta TF_SECONDS.' + k); fallos++; }
});
console.log('  S10 = ' + P.CONFIG.TF_SECONDS.S10 + 's (antes no existia: se leia M30 = ' +
  P.CONFIG.TF_SECONDS.M30 + 's)');

// El archivo con la rejilla CORRECTA crece; con la equivocada no.
const velasArch = casos['RANGO LATERAL (oscila en canal)'];
// El dano real del timeframe mal leido: con la rejilla equivocada
// dos escaneos separados en el tiempo caen en los MISMOS huecos y
// el archivo se sobrescribe a si mismo en vez de crecer. Se simula
// avanzando el reloj 60s entre escaneo y escaneo.
function conReloj(ms, fn) {
  const prev = sandbox.Date;
  sandbox.Date = { now: () => ms };
  try { return fn(); } finally { sandbox.Date = prev; }
}
const t0 = Date.now();
const lote = velasArch.slice(0, 40);
conReloj(t0,         () => P.CandleArchive.add('TF-BIEN', 10, lote));
const archBien = conReloj(t0 + 60000, () => P.CandleArchive.add('TF-BIEN', 10, lote));
conReloj(t0,         () => P.CandleArchive.add('TF-MAL', 1800, lote));
const archMal = conReloj(t0 + 60000, () => P.CandleArchive.add('TF-MAL', 1800, lote));
console.log('  dos escaneos con 60s de diferencia, 40 velas cada uno:');
console.log('    rejilla S10 (correcta):   ' + archBien + ' velas archivadas');
console.log('    rejilla M30 (el bug):     ' + archMal + ' velas archivadas');
if (archBien <= 40) { console.log('  !! con la rejilla correcta el archivo deberia crecer'); fallos++; }
if (archMal !== 40) { console.log('  !! con la rejilla de 30 min no deberia crecer'); fallos++; }

console.log('\n=== v4.4.2 HISTORIAL LEGACY SEPARADO ===');
const bl = P.History.backtests();
console.log('  nuevas: ' + JSON.stringify(bl.total) + ' | legacy: ' + JSON.stringify(bl.legacy));
if (bl.legacy.n !== 0) { console.log('  !! no deberia haber legacy tras clear()'); fallos++; }
if (bl.total.n !== 5) { console.log('  !! las 5 nuevas no cuentan'); fallos++; }

console.log('\n=== v4.4.5 ACIERTO SIN SENALES CERRADAS ===');
// Con solo EMPATE y PENDIENTE el acierto es DESCONOCIDO, no 0%
P.History.clear();
P.History.add({ asset: 'E', dir: 'CALL', score: 70, quality: 'MEDIUM',
  refPrice: 1, refReal: true, refT: Date.now() - 61000, tfSec: 60,
  deadline: Date.now() - 1000, tag: 'NORMAL', refMethod: 'eje' });
P.History.update(1);                    // no se movio -> EMPATE
const sE = P.History.stats();
console.log('  ' + sE.wins + 'W/' + sE.losses + 'L/' + sE.ties + 'E -> acc=' +
  sE.acc + ' decididas=' + sE.decididas);
if (sE.acc !== null) { console.log('  !! deberia ser null, no ' + sE.acc); fallos++; }
if (sE.ties !== 1) { console.log('  !! el empate no se registro'); fallos++; }
// Y con una decidida, el acierto vuelve a ser un numero
P.History.add({ asset: 'F', dir: 'CALL', score: 70, quality: 'MEDIUM',
  refPrice: 1, refReal: true, refT: Date.now() - 61000, tfSec: 60,
  deadline: Date.now() - 1000, tag: 'NORMAL', refMethod: 'eje' });
P.History.update(2);                    // subio -> WIN
const sW = P.History.stats();
console.log('  ' + sW.wins + 'W/' + sW.losses + 'L/' + sW.ties + 'E -> acc=' + sW.acc + '%');
if (sW.acc !== 100) { console.log('  !! deberia ser 100'); fallos++; }
P.History.clear();

// ============================================================
// v4.4.6: el MTF SINTETICO no puede contar como confirmacion.
// Se fabrica agrupando las MISMAS velas del timeframe actual, asi
// que su tendencia ES la tendencia local: votar con el infla la
// confluencia con evidencia repetida. Lo vio el usuario en una
// senal PUT 95/100 apoyada en "Tendencia DOWN" + "MTF M1*:BAJISTA".
// ============================================================
console.log('\n=== v4.4.6 MTF SINTETICO NO CONFIRMA ===');
const bajista = serie(90, i => 200 + i * 2);        // precio cayendo
// Solo se ha escaneado UN timeframe: el MTF solo puede ser sintetico
P.CandleArchive.add('MTF-SOLO', 30, bajista);
const ctxSyn = P.CandleArchive.higherTrend('MTF-SOLO', 30);
console.log('  un solo timeframe -> real=' + ctxSyn.real + ' sinteticas=' +
  ctxSyn.syn + ' | ' + (ctxSyn.used.join(' ') || 'sin series'));
if (ctxSyn.real !== 0) { console.log('  !! no deberia haber series reales'); fallos++; }
if (!ctxSyn.syn) { console.log('  !! deberia derivar alguna sintetica'); fallos++; }

const conSyn = P.Scoring.evaluate(bajista, { asset: 'MTF-SOLO', tfSec: 30 });
const confSyn = parseInt(conSyn.detail.confluencia, 10);
console.log('  score=' + conSyn.score + ' confluencia=' + conSyn.detail.confluencia +
  ' | contexto: ' + conSyn.detail.contexto.slice(0, 62) + '...');
if (!/SINTETICO/.test(conSyn.detail.contexto)) {
  console.log('  !! el panel no avisa de que es sintetico'); fallos++;
}

// Ahora SI existe una serie real de un timeframe mayor: debe votar
P.CandleArchive.add('MTF-REAL', 30, bajista);
P.CandleArchive.add('MTF-REAL', 300, bajista);      // M5 archivado de verdad
const ctxReal = P.CandleArchive.higherTrend('MTF-REAL', 30);
console.log('  con M5 archivado   -> real=' + ctxReal.real + ' sinteticas=' +
  ctxReal.syn + ' dirReal=' + ctxReal.dirReal);
if (ctxReal.real < 1) { console.log('  !! deberia contar la serie real'); fallos++; }

const conReal = P.Scoring.evaluate(bajista, { asset: 'MTF-REAL', tfSec: 30 });
const confReal = parseInt(conReal.detail.confluencia, 10);
console.log('  confluencia sin MTF real: ' + confSyn + '/12  ->  con MTF real: ' +
  confReal + '/12');
if (confReal <= confSyn) {
  console.log('  !! un MTF real deberia sumar una fuente mas'); fallos++;
}

console.log('\n===== ' + (fallos ? fallos + ' FALLOS' : 'TODAS LAS COMPROBACIONES OK') + ' =====');
process.exit(fallos ? 1 : 0);
