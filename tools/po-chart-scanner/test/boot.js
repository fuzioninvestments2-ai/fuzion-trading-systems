// ============================================================
// boot.js - Prueba de ARRANQUE de la extension completa.
//
// smoke.js prueba el motor de senales; esto prueba lo otro: que
// los 20 modulos carguen en el orden del manifest y que el panel
// se monte sin lanzar una excepcion. Un fallo aqui es justo el
// sintoma de "no escanea, no hace ninguna funcion": si un modulo
// revienta al cargarse, los siguientes no ven su objeto y el
// injector no llega a montar nada.
//
//   node test/boot.js <carpeta-de-la-extension>
// ============================================================
const fs = require('fs'), vm = require('vm'), path = require('path');
const BASE = process.argv[2] || '.';
const manifest = JSON.parse(fs.readFileSync(path.join(BASE, 'manifest.json'), 'utf8'));
const ORDEN = manifest.content_scripts[0].js;

let fallos = 0;
const timers = [];                      // setInterval/setTimeout capturados

// ---------- DOM minimo ----------
function elemento(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    id: '', textContent: '', innerHTML: '', innerText: '',
    children: [], dataset: {}, style: {}, value: undefined,
    parentElement: null,
    appendChild(c) { this.children.push(c); c.parentElement = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    remove() { if (this.parentElement) this.parentElement.removeChild(this); },
    addEventListener() {}, removeEventListener() {},
    setAttribute(k, v) { this[k] = v; }, getAttribute(k) { return this[k]; },
    // el panel busca sus propias celdas: siempre devolver algo usable
    querySelector() { return elemento('span'); },
    querySelectorAll() { return []; },
    closest() { return null; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 20,
                                       right: 100, bottom: 20 }; },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } }
  };
  return el;
}
const body = elemento('body');
body.innerText = 'EUR/USD OTC +92% S10 00:00:15 1.23456';

const store = {};
const sandbox = {
  console: Object.assign(Object.create(console), { table: () => {} }),
  document: {
    body: body,
    createElement: elemento,
    createElementNS: (ns, tag) => elemento(tag),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {}
  },
  getComputedStyle: () => ({ backgroundColor: 'rgba(0, 0, 0, 0)', fontSize: '12px' }),
  innerWidth: 1900, innerHeight: 900,
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; }
  },
  setInterval: (fn, ms) => { timers.push({ fn: fn, ms: ms, tipo: 'interval' }); return timers.length; },
  clearInterval: () => {},
  setTimeout: (fn, ms) => { timers.push({ fn: fn, ms: ms, tipo: 'timeout' }); return timers.length; },
  clearTimeout: () => {},
  chrome: { runtime: { sendMessage: () => {}, lastError: null,
                       onMessage: { addListener: () => {} },
                       onInstalled: { addListener: () => {} } },
            tabs: { captureVisibleTab: () => {} } },
  Date, Math, JSON, Object, Array, String, Number, Promise, Image: function () {},
  isFinite, parseInt, parseFloat, RegExp, Error
};
sandbox.window = sandbox;
sandbox.window.addEventListener = () => {};
vm.createContext(sandbox);

// ---------- 1) cargar los modulos en el ORDEN DEL MANIFEST ----------
console.log('=== CARGA DE MODULOS (orden del manifest) ===');
ORDEN.forEach(rel => {
  const f = path.join(BASE, rel);
  try {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: rel });
    console.log('  ok   ' + rel);
  } catch (e) {
    console.log('  FALLO ' + rel + ' -> ' + e.message);
    fallos++;
  }
});

const P = sandbox.POScannerPRO;
if (!P) { console.log('!! POScannerPRO no existe'); process.exit(1); }

// ---------- 2) los 20 modulos deben haberse registrado ----------
console.log('\n=== REGISTRO DE MODULOS ===');
const NEED = ['config','canvasReader','indicators','patternDetector','supportResistance',
              'trendAnalyzer','candleArchive','scoring','confirmators','adaptiveFormulas',
              'areaSelector','chartOverlay','history','alerts','panel','injector',
              'trapDetector','orderFlowDetector','crowdBehavior','contrarianScoring'];
const faltan = NEED.filter(n => (P._mods || []).indexOf(n) < 0);
console.log('  registrados: ' + (P._mods || []).length + '/20' +
  (faltan.length ? ' | FALTAN: ' + faltan.join(', ') : ''));
if (faltan.length) fallos++;

// ---------- 3) los objetos publicos deben existir ----------
console.log('\n=== OBJETOS PUBLICOS ===');
[['Panel','mount'], ['Scoring','evaluate'], ['CanvasReader','readBest'],
 ['History','add'], ['CandleArchive','add'], ['ChartOverlay','draw'],
 ['ContrarianScoring','adjust'], ['TrapDetector','analyze'],
 ['OrderFlowDetector','analyze'], ['CrowdBehavior','analizar'],
 ['Alerts','beep'], ['Indicators','rsi'], ['SupportResistance','findLevels'],
 ['TrendAnalyzer','analyze'], ['PatternDetector','detect']].forEach(([obj, fn]) => {
  const ok = P[obj] && typeof P[obj][fn] === 'function';
  if (!ok) { console.log('  FALTA ' + obj + '.' + fn + '()'); fallos++; }
});
console.log('  15 objetos publicos comprobados');

// ---------- 4) el injector debe haber programado su arranque ----------
console.log('\n=== ARRANQUE DEL INJECTOR ===');
const boot = timers.filter(t => t.tipo === 'interval' && t.ms === 500);
console.log('  temporizador de arranque programado: ' + (boot.length ? 'si' : 'NO'));
if (!boot.length) fallos++;
else {
  try {
    boot[0].fn();                       // dispara init() -> Panel.mount()
    console.log('  init() ejecutado sin excepcion');
  } catch (e) {
    console.log('  FALLO en init(): ' + e.message + '\n' + (e.stack || '').split('\n')[1]);
    fallos++;
  }
}

// ---------- 5) el panel debe responder a sus metodos ----------
console.log('\n=== PANEL VIVO ===');
try {
  P.Panel.set('status', 'prueba');
  P.Panel.setAuto(true); P.Panel.setAuto(false);
  P.Panel.setVisible(false); P.Panel.setVisible(true);
  const tf = P.Panel.getTfSec(), tt = P.Panel.getTradeSec();
  const exp = P.Panel.expiryInfo();
  console.log('  tfSec=' + tf + ' tradeSec=' + tt + ' expira="' + exp.text + '"');
  P.Panel.showHistory();
  console.log('  set/setAuto/setVisible/expiryInfo/showHistory: sin excepcion');
} catch (e) {
  console.log('  FALLO en el panel: ' + e.message + '\n' + (e.stack || '').split('\n')[1]);
  fallos++;
}

// ---------- 6) un resultado real debe poder pintarse ----------
console.log('\n=== PINTAR UN RESULTADO ===');
try {
  const velas = [];
  for (let i = 0; i < 60; i++) {
    const mid = 300 + Math.sin(i / 5) * 20;
    velas.push({ x: i * 6, width: 4, dir: i % 2 ? 'CALL' : 'PUT',
      high: mid - 8, low: mid + 8, open: mid + 4, close: mid - 4,
      bodyTop: mid - 4, bodyBottom: mid + 4, bodySize: 8, wickUp: 4, wickDown: 4 });
  }
  const r = P.Scoring.evaluate(velas, { asset: 'EUR/USD OTC', tfSec: 10 });
  P.Panel.showResult(r);
  console.log('  showResult(' + r.dir + ' ' + r.score + ') sin excepcion');
  P.ChartOverlay.draw(velas, { left: 0, top: 0, sx: 1, sy: 1 },
                      P.SupportResistance.findLevels(velas), r);
  console.log('  ChartOverlay.draw() sin excepcion');
} catch (e) {
  console.log('  FALLO al pintar: ' + e.message + '\n' + (e.stack || '').split('\n')[1]);
  fallos++;
}

console.log('\n===== ARRANQUE: ' + (fallos ? fallos + ' FALLOS' : 'OK, la extension arranca') + ' =====');
process.exit(fallos ? 1 : 0);
