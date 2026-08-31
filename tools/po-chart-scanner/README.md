# PO Chart Scanner PRO v4.4.0 — OPTIMIZACION DE SCORING Y FILTRADO

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
- evaluacion WIN/LOSS del historial con precio real;
- v4.4: el umbral de confluencia bloquea lo que debe, las diez etiquetas de
  accion mapean al rango correcto, el setup perfecto no se marca sin muestra
  de backtest (y dice que condicion falta), y las tres categorias de backtest
  cuadran.

## Arquitectura

| Capa | Archivos |
|---|---|
| Lectura de pixeles | `canvasReader.js` (Motor 1: canvas; Motor 2: captura via service worker) |
| Indicadores | `indicators.js` (RSI, Estocastico 14/3/3, Momentum, MACD, EMA9/SMA10) |
| Estructura | `patternDetector.js`, `supportResistance.js`, `trendAnalyzer.js` |
| Memoria propia | `candleArchive.js` (historial profundo en localStorage, re-anclaje de escala, backtest) |
| Anti-manipulacion | `trapDetector.js`, `orderFlowDetector.js`, `crowdBehavior.js`, `contrarianScoring.js` |
| Decision | `scoring.js` (votacion + confluencia + techos estructurales + capa contrarian + regla de los 90 + umbral de confluencia) |
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

## v4.4: etiquetas de accion y umbral de confluencia

### Etiqueta de accion (`FILTER`)

El panel traduce el score a una orden, para no tener que decidirlo
mentalmente. Los rangos son configurables en `CONFIG.FILTER`:

| Score | Etiqueta | Color |
|---|---|---|
| 90-100 | `OPERAR` | verde brillante |
| 85-89 | `OPERAR SI CONTRARIAN` (o `OPERAR (CONTRARIAN)` si lo es) | verde |
| 75-84 | `RIESGO MEDIO` | amarillo |
| 60-74 | `NO OPERAR` | naranja |
| < 60 | `NO OPERAR - SCORE BAJO` | rojo |
| cualquiera, si `blocked` | `BLOQUEADA - NO OPERAR` | rojo |

Ademas: por debajo de `FILTER.ENTRY_MIN` (75) el grafico **no dibuja flecha
ni linea de entrada** — solo una nota amarilla; y entre 75 y `WEAK_WARN` (85)
el panel avisa "Senal debil, esperar mejor setup".

### Umbral de confluencia (`FILTER.MIN_CONFLUENCIA`)

Con menos de 7 de 12 fuentes coincidiendo, la senal se bloquea aunque su
porcentaje sea alto. La razon es que el score mide el **reparto** de votos
(ganador / total), no cuantas fuentes votaron: 2 contra 0 da 100%. Un setup
contrarian perfecto baja el listado a 6/12.

**Esto reduce muchisimo el numero de senales.** En las cuatro series
sinteticas del arnes, las cuatro quedan bloqueadas por este umbral (dan 5-6
de 12), y la captura en vivo de AUD/CHF OTC que motivo esta version marcaba
6/12 — tambien quedaria bloqueada. Es el comportamiento pedido, pero si el
bot deja de emitir senales durante horas, `FILTER.MIN_CONFLUENCIA` es la
perilla: bajarlo a 6 recupera el ritmo de la v4.3.

### Setup contrarian perfecto (`PERFECT`)

Seis condiciones, todas obligatorias: nivel S/R con 3+ toques, fakeout
detectado, senal contrarian, confluencia 8/12, backtest contrarian por encima
del 65% y trap index por debajo del 70%. Si se cumplen: **+15 puntos y piso
de 90**, y queda exento de la regla de los 90. Si no, el panel enumera que
condicion falta.

La condicion del backtest **no** usa un backtest por patron — no existe. Usa
el acierto real de tus propias senales CONTRARIAN ya vencidas
(`History.byTag`), y exige muestra minima (`BACKTEST_MIN_N`, 10 por defecto).
Sin muestra la condicion cuenta como no cumplida y lo dice: `backtest
contrarian >65% (muestra 0/10)`. Pon `PERFECT.REQUIRE_BACKTEST` en `false`
para no exigirla mientras acumulas.

### Backtest separado

`History.backtests()` devuelve tres categorias — `contrarian`, `normal`,
`total` — y el panel las muestra en linea aparte. Es el acierto **real** de
las senales que este bot emitio y ya vencieron, distinto del backtest de
`CandleArchive`, que es una simulacion sobre el archivo de velas.

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

### v4.4.0

- `contrarianScoring.js`: setup contrarian perfecto (+15 y piso 90) con las
  seis condiciones, y lista de las que faltan cuando no llega.
- `scoring.js`: umbral de confluencia (7/12, 6/12 si el setup es perfecto) y
  exencion del perfecto en la regla de los 90; expone `perfecto` y `agree`.
- `panel.js`: etiqueta de accion, aviso de senal debil, backtest separado en
  el detalle y en la vista HISTORIAL.
- `chartOverlay.js`: sin flecha ni linea de entrada por debajo de `ENTRY_MIN`.
- `history.js`: `backtests()` con las tres categorias.
- `panel.css`: colores de las etiquetas.

Nada de la v4.3 se quito: siguen el bloqueo contra-estructura, trap index,
reversal ratio, masa obvia, score con velas cerradas y backtest maduro.

**Lo que esta version NO hace:** subir el score de un setup no lo vuelve mas
acertado. El +15 del setto perfecto y las etiquetas cambian como se presenta
la senal, no su probabilidad. Lo unico que puede mover el resultado real es
operar menos y mejor (el umbral de confluencia); mide el backtest CONTRARIAN
separado antes de dar por buena la mejora.

### v4.3.1 (integrada desde el instalador del usuario)

- Los avisos de la capa contrarian viajan en `contraNote` y ya no se mezclan en
  `warning`. El panel pinta `warning` como "CONTRA-ESTRUCTURA - Riesgo Alto",
  asi que una senal CONTRARIAN buena salia marcada como peligrosa.
- Una senal ya bloqueada por estructura no recibe encima los castigos de trap
  index, fakeout ni masa obvia (castigo doble sobre una senal ya muerta).
