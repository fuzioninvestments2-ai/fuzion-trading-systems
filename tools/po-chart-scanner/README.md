# PO Chart Scanner PRO v4.3.1 — CONTRARIAN ANTI-MANIPULACION

Extension de Chrome (Manifest V3) que lee el grafico de Pocket Option **por
pixeles** y produce una senal CALL/PUT puntuada. No opera sola: `AUTOTRADE`
esta desactivado por diseno y no hay ninguna ruta de codigo que envie ordenes.

Herramienta educativa. No garantiza resultados.

## Instalacion (3 pasos)

1. Copia todo el contenido de `install-po-chart-scanner.ps1`.
2. Pegalo en PowerShell y pulsa Enter. Crea
   `Documentos\PO-Chart-Scanner-PRO-v4.3` (no toca otras versiones).
3. Chrome -> `chrome://extensions` -> *Modo de desarrollador* -> *Cargar sin
   empaquetar* -> selecciona esa carpeta.

Como alternativa puedes cargar directamente esta carpeta (`tools/po-chart-scanner`)
sin empaquetar; el `.ps1` solo existe para instalar en una maquina sin el repo.

## El instalador se genera, no se edita

`install-po-chart-scanner.ps1` se deriva de los archivos de esta carpeta:

```bash
python3 scripts/build_po_scanner_installer.py          # regenerar
python3 scripts/build_po_scanner_installer.py --check  # verificar sincronia
```

El generador comprueba el *round-trip*: extrae de nuevo cada here-string del
`.ps1` y lo compara byte a byte con el archivo del repo. Asi el instalador y
el codigo no pueden divergir.

## Verificacion

```bash
# sintaxis de los 21 modulos JS + validez del manifest
for f in $(find tools/po-chart-scanner -name '*.js'); do node --check "$f"; done
python3 -m json.tool tools/po-chart-scanner/manifest.json > /dev/null

# prueba funcional del motor de senales (sin navegador)
node tools/po-chart-scanner/test/smoke.js tools/po-chart-scanner
```

`test/smoke.js` carga los 12 modulos de analisis en Node con stubs de
`window`/`document`/`localStorage`, corre el pipeline sobre velas sinteticas
(tendencia alcista, bajista, rango lateral, caida con giro) y comprueba:

- rango y tipo del score, direccion valida;
- que los techos estructurales solo bajan el score (salvo el bonus
  CONTRARIAN, que es la unica via de subida);
- direccionalidad correcta en tendencias claras;
- deduplicacion del archivo de velas por rejilla de cierre;
- backtest y contexto MTF sintetico;
- evaluacion WIN/LOSS del historial con precio real.

## Arquitectura

| Capa | Archivos |
|---|---|
| Lectura de pixeles | `canvasReader.js` (Motor 1: canvas; Motor 2: captura via service worker) |
| Indicadores | `indicators.js` (RSI, Estocastico 14/3/3, Momentum, MACD, EMA9/SMA10) |
| Estructura | `patternDetector.js`, `supportResistance.js`, `trendAnalyzer.js` |
| Memoria propia | `candleArchive.js` (historial profundo en localStorage, re-anclaje de escala, backtest) |
| Anti-manipulacion | `trapDetector.js`, `orderFlowDetector.js`, `crowdBehavior.js`, `contrarianScoring.js` |
| Decision | `scoring.js` (votacion + confluencia + techos estructurales + capa contrarian + regla de los 90) |
| Interfaz | `panel.js`, `chartOverlay.js`, `history.js`, `alerts.js`, `content/injector.js` |
| Sin implementar | `confirmators.js`, `adaptiveFormulas.js`, `areaSelector.js` (stubs registrados) |

## Limitaciones conocidas

- **Dominios.** `manifest.json` solo inyecta en `pocketoption.com` y
  `app.pocketoption.com`. En un espejo regional (`po.trade`, `m.pocketoption.com`,
  etc.) la extension no carga: hay que anadir el dominio a `content_scripts.matches`.
- **No hay volumen real.** El grafico solo da pixeles. El "order flow" se
  infiere del **rango** de la vela y la "masa" de lo obvia que es la senal;
  son proxies declarados, no datos del broker.
- **El backtest es del propio archivo.** Mide la votacion ligera
  (`quickEvaluate`) contra las velas que el bot fue guardando, no contra un
  feed historico independiente. Por eso el panel no muestra el porcentaje
  hasta acumular `BT_MIN_SHOW` (30) senales.
- **`blocked` se decide antes de la capa contrarian.** Un bonus contrarian
  puede dejar el score final por encima de `rawScore`; es intencionado, pero
  significa que `rawScore` es "antes del techo estructural", no "antes de todo".
- **El castigo de order flow no respeta `yaBloqueada`.** En v4.3.1 los castigos
  de trap / fakeout / masa se saltan cuando la senal ya esta bloqueada, pero el
  de order flow (`FLOW_PENALTY`) se sigue aplicando. Sin efecto visible (el
  panel muestra `rawScore` en las bloqueadas), pero es una inconsistencia con
  la intencion declarada del fix.
- **`findCurrentPrice()` puede no encontrar el precio del eje.** Cuando el
  panel dice `precio: archivo` en la linea de estado, el WIN/LOSS no se juzga
  con el precio real del DOM sino con la escala en pixeles del archivo, que es
  bastante menos fiable. Ver la seccion siguiente.
- **Modulos duplicados.** Si hay otra version del panel PRO activa a la vez,
  esta copia se queda dormida (lo avisa por consola). Desactiva la otra en
  `chrome://extensions`.

## Diagnostico: `precio: archivo` en la linea de estado

Si el estado del panel termina en `| precio: archivo`, `findCurrentPrice()`
devolvio `null`: no encontro la etiqueta del precio actual pegada al eje
derecho. Consecuencia: todas las senales se guardan con `refReal: false` y el
WIN/LOSS se decide comparando cierres en **pixeles** de la escala del archivo,
con `EMPATE` para cualquier movimiento menor de 0.5 px. Eso explica una
proporcion alta de empates en la celda ACIERTO.

Para comprobarlo, en la consola de Pocket Option (F12 -> Console):

```js
POScannerPRO.Panel.findCurrentPrice()   // null = no lo esta leyendo
```

El selector busca un nodo hoja con texto tipo `1.2345`, en la franja
horizontal 55%-95% del ancho, y con fondo pintado en el propio nodo o hasta 3
niveles por encima. Si PO cambio ese marcado, hay que ajustar la funcion en
`src/panel.js`.

## Cambios respecto al script original pegado

En `scoring.js`, fuente 5 (histograma MACD), la rama bajista sumaba el punto a
`putPts` pero contaba la fuente en `callSrc`:

```js
else if (mf.hist < 0 && !mf.rising) { putPts += 1; callSrc++; }   // antes
else if (mf.hist < 0 && !mf.rising) { putPts += 1; putSrc++; }    // ahora
```

`callSrc`/`putSrc` alimentan la confluencia, que da hasta +15 puntos de bonus
y decide la regla de los 90 y la deteccion de senal "obvia". El error inflaba
la confluencia CALL y desinflaba la PUT en cualquier grafico con MACD bajista.

**Ojo al regenerar desde un script pegado:** la v4.3.1 que llego por PowerShell
se habia construido sobre el script original y traia este bug otra vez. Al
integrarla se conservo la correccion. Por eso el `.ps1` se genera desde el
repo y no al reves.

### v4.3.1 (integrada desde el instalador del usuario)

- Los avisos de la capa contrarian viajan en `contraNote` y ya no se mezclan en
  `warning`. El panel pinta `warning` como "CONTRA-ESTRUCTURA - Riesgo Alto",
  asi que una senal CONTRARIAN buena salia marcada como peligrosa.
- Una senal ya bloqueada por estructura no recibe encima los castigos de trap
  index, fakeout ni masa obvia (castigo doble sobre una senal ya muerta).
