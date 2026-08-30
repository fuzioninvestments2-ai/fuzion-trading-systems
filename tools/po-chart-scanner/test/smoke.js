// Arnes de prueba: carga los modulos de analisis del PO Chart Scanner
// en Node con stubs minimos de window/document/localStorage y ejecuta
// el pipeline de scoring sobre velas sinteticas.
const fs = require('fs'), vm = require('vm'), path = require('path');
const BASE = process.argv[2];

const store = {};
const sandbox = {
  console,
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
  'crowdBehavior','contrarianScoring','scoring','history'];
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
  console.log('  trapIndex=' + d.trapIndex + '%  reversalRatio=' + d.reversalRatio +
              '  fakeout=' + d.fakeout + '  actividad=' + d.actividad +
              '  contrarian=' + r.contrarian + '  obvia=' + r.esObvia);
  // Invariantes que deben cumplirse SIEMPRE
  const inv = [
    ['score en 0..100', r.score >= 0 && r.score <= 100],
    ['score numerico', Number.isFinite(r.score)],
    ['dir valido', r.dir === 'CALL' || r.dir === 'PUT'],
    ['score <= rawScore + bonus contrarian', r.score <= r.rawScore + P.CONFIG.CONTRARIAN.FAKEOUT_BONUS],
    ['bonus por encima del techo SOLO si es contrarian', r.score <= r.rawScore || r.contrarian],
    ['trapIndex 0..100', d.trapIndex >= 0 && d.trapIndex <= 100],
    ['bloqueada => no confirmada como entrada util', !(r.blocked && r.score > r.rawScore)]
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

console.log('\n===== ' + (fallos ? fallos + ' FALLOS' : 'TODAS LAS COMPROBACIONES OK') + ' =====');
process.exit(fallos ? 1 : 0);
