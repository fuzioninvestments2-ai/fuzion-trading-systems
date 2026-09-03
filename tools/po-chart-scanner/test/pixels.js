// ============================================================
// pixels.js - Prueba del LECTOR DE PIXELES con imagenes sinteticas.
//
// Reproduce la pantalla real: velas de PO mas las dos MEDIAS
// MOVILES (roja y verde lima, los mismos colores que las velas y
// CONTINUAS de lado a lado). Ese fue el fallo que dejo al usuario
// con "captura: 4 velas / 17513 px": la media cruzaba el hueco
// entre velas, el agrupador las pegaba todas y el bloque
// resultante se descartaba por ancho.
//
// Se prueba con el grafico REDUCIDO (velas finas) y AMPLIADO
// (velas anchas) porque el fallo solo aparecia al ampliar.
//
//   node test/pixels.js <carpeta-de-la-extension>
// ============================================================
const fs = require('fs'), vm = require('vm'), path = require('path');
const BASE = process.argv[2] || '.';
const sandbox = { console, document: { querySelector: () => null },
  Math, JSON, Object, Array, Number, isFinite, parseInt, parseFloat };
sandbox.window = sandbox; sandbox.window.addEventListener = () => {};
vm.createContext(sandbox);
['src/config.js', 'src/canvasReader.js'].forEach(f =>
  vm.runInContext(fs.readFileSync(path.join(BASE, f), 'utf8'), sandbox, { filename: f }));
const P = sandbox.POScannerPRO;

const VERDE = [60, 200, 90];    // lima de las velas PO
const ROJO  = [230, 40, 60];
const FONDO = [17, 24, 32];

function lienzo(W, H) {
  const a = new Array(W * H * 4);
  for (let i = 0; i < W * H; i++) {
    a[i*4] = FONDO[0]; a[i*4+1] = FONDO[1]; a[i*4+2] = FONDO[2]; a[i*4+3] = 255;
  }
  return a;
}
function pinta(img, W, H, x, y, c) {
  if (x < 0 || x >= W || y < 0 || y >= H) return;
  const i = (y * W + x) * 4;
  img[i] = c[0]; img[i+1] = c[1]; img[i+2] = c[2]; img[i+3] = 255;
}

// o = { W,H,n,ancho,paso,cuerpo,mecha,medias,grosorMedia,macd }
function grafico(o) {
  const W = o.W, H = o.H, img = lienzo(W, H);
  for (let k = 0; k < o.n; k++) {
    const x0 = 8 + k * o.paso;
    const mid = H * 0.45 + Math.sin(k / 3.5) * (H * 0.18);
    const col = k % 2 ? VERDE : ROJO;
    const top = Math.round(mid - o.cuerpo / 2), bot = Math.round(mid + o.cuerpo / 2);
    for (let x = x0; x < x0 + o.ancho; x++)
      for (let y = top; y <= bot; y++) pinta(img, W, H, x, y, col);
    const cx = x0 + (o.ancho >> 1);
    for (let y = top - o.mecha; y <= bot + o.mecha; y++) {
      pinta(img, W, H, cx, y, col);
      if (o.ancho > 3) pinta(img, W, H, cx + 1, y, col);
    }
  }
  if (o.medias) {
    const g = o.grosorMedia || 3;
    for (let x = 0; x < W; x++) {
      const yr = Math.round(H * 0.45 + Math.sin(x / (W / 7)) * (H * 0.15));
      const yv = Math.round(H * 0.45 + Math.sin(x / (W / 7) + 0.6) * (H * 0.15));
      for (let d = 0; d < g; d++) {
        pinta(img, W, H, x, yr + d, ROJO);
        pinta(img, W, H, x, yv + d, VERDE);
      }
    }
  }
  if (o.macd) {           // panel de indicadores DEBAJO, otra zona vertical
    const base = Math.round(H * 0.85);
    for (let k = 0; k < o.n; k++) {
      const x0 = 8 + k * o.paso;
      const alto = 4 + (k % 5) * 3;
      const col = k % 3 ? VERDE : ROJO;
      for (let x = x0; x < x0 + o.ancho; x++)
        for (let y = base; y <= base + alto; y++) pinta(img, W, H, x, y, col);
    }
  }
  return img;
}

const CASOS = [
  { nombre: 'reducido, sin medias',
    o: { W: 600, H: 300, n: 60, ancho: 4, paso: 9, cuerpo: 26, mecha: 8 }, min: 50 },
  { nombre: 'reducido, CON medias',
    o: { W: 600, H: 300, n: 60, ancho: 4, paso: 9, cuerpo: 26, mecha: 8,
         medias: true }, min: 45 },
  { nombre: 'ampliado, sin medias',
    o: { W: 600, H: 300, n: 20, ancho: 18, paso: 26, cuerpo: 40, mecha: 12 }, min: 18 },
  { nombre: 'ampliado, CON medias  <- el caso del usuario',
    o: { W: 600, H: 300, n: 20, ancho: 18, paso: 26, cuerpo: 40, mecha: 12,
         medias: true }, min: 18 },
  { nombre: 'muy ampliado, medias gruesas',
    o: { W: 700, H: 320, n: 12, ancho: 34, paso: 52, cuerpo: 60, mecha: 16,
         medias: true, grosorMedia: 5 }, min: 10 },
  { nombre: 'ampliado + medias + panel MACD debajo',
    o: { W: 600, H: 340, n: 20, ancho: 18, paso: 26, cuerpo: 40, mecha: 12,
         medias: true, macd: true }, min: 18 }
];

let fallos = 0;
console.log('=== LECTOR DE PIXELES (velas + medias moviles) ===');
CASOS.forEach(c => {
  const velas = P.CanvasReader.extractCandles(grafico(c.o), c.o.W, c.o.H);
  const ok = velas.length >= c.min && velas.length <= c.o.n + 4;
  console.log('  ' + c.nombre.padEnd(40) + ' esperadas ~' + c.o.n +
    ' (min ' + c.min + ')  leidas ' + String(velas.length).padStart(3) +
    (ok ? '  OK' : '  FALLO'));
  if (!ok) fallos++;
});

// El filtro de ancho debe seguir descartando un boton BUY/SELL
const W = 400, H = 200, boton = lienzo(W, H);
for (let x = 100; x < 240; x++) for (let y = 60; y < 110; y++) pinta(boton, W, H, x, y, VERDE);
const velasBoton = P.CanvasReader.extractCandles(boton, W, H);
const okBoton = velasBoton.length === 0;
console.log('  ' + 'boton verde de 140px no es una vela'.padEnd(40) +
  ' leidas ' + velasBoton.length + (okBoton ? '  OK' : '  FALLO'));
if (!okBoton) fallos++;

console.log('\n===== PIXELES: ' + (fallos ? fallos + ' FALLOS' : 'TODO OK') + ' =====');
process.exit(fallos ? 1 : 0);
