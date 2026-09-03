# PO Chart Scanner PRO v4.4.5 — OPTIMIZACION DE SCORING Y FILTRADO

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
# sintaxis de los modulos JS + validez del manifest
for f in $(find tools/po-chart-scanner -name '*.js'); do node --check "$f"; done
python3 -m json.tool tools/po-chart-scanner/manifest.json > /dev/null

# las tres suites
node tools/po-chart-scanner/test/boot.js   tools/po-chart-scanner  # arranca?
node tools/po-chart-scanner/test/pixels.js tools/po-chart-scanner  # lee velas?
node tools/po-chart-scanner/test/smoke.js  tools/po-chart-scanner  # decide bien?
```

`test/boot.js` carga los 20 modulos **en el orden del manifest** con un DOM
simulado y monta el panel. Un fallo aqui es el sintoma de "no hace ninguna
funcion": si un modulo revienta al cargarse, los siguientes no ven su objeto.

`test/pixels.js` dibuja graficos sinteticos (velas + las dos medias moviles de
PO, que son del MISMO color que las velas y continuas) y comprueba cuantas
velas extrae el lector, con el grafico reducido y ampliado.

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
  cuadran;
- v4.4.1: nueve casos de seleccion del precio del eje sobre un DOM simulado;
- v4.4.3: la deteccion del timeframe elige el chip activo y no el primer
  token de la pagina (cinco casos), los timeframes cortos existen en la tabla,
  y dos escaneos separados 60s hacen crecer el archivo con la rejilla correcta
  (46 velas) mientras que con la rejilla de 30 minutos se queda en 40;
- v4.4.2: la calibracion del eje traduce pixeles a precio con error nulo,
  rechaza un eje incoherente o invertido en vez de inventar un numero, las
  senales de 6/12 se desbloquean, un setup contrarian perfecto completo llega
  a 90+ (97 en la prueba) y las legacy quedan separadas.

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

## Diagnostico: "Sin velas suficientes" con muchos pixeles

Si el panel dice algo como `captura: 4 velas / 17513 px`, encontro color de
sobra pero no supo separarlo en velas. La causa tipica son las **medias
moviles**: en PO son roja y verde lima, exactamente los colores de las velas,
y son continuas de lado a lado. En el hueco entre dos velas lo unico coloreado
es la media, del mismo color y a la misma altura, asi que hasta v4.4.3 el
agrupador la tomaba por continuacion de la vela y pegaba una con la siguiente
hasta superar `MAX_WIDTH_PX`, momento en el que descartaba el bloque entero.

Con el grafico **ampliado** (pocas velas muy anchas) esto se comia casi toda
la lectura. Desde v4.4.4:

- una columna cuyo tramo vertical es mucho mas bajo que la vela en curso
  (`CANDLE.LINE_RATIO`, 35%) **corta** el grupo en vez de alargarlo;
- los restos de linea que quedan se separan de las velas buscando las **dos
  poblaciones de altura** (se corta por el salto relativo mas grande, y solo
  si ese salto es de 3x o mas);
- `MAX_WIDTH_PX` sube de 30 a 60 px, porque una vela de un grafico ampliado
  pasa de 30 con facilidad. Los botones BUY/SELL rondan los 110 px y siguen
  fuera.

Si aun asi lee pocas velas, prueba a **reducir el zoom del grafico** o a usar
el boton GRAFICO y sombrear solo la zona de velas.

## Diagnostico: el timeframe del panel no coincide con el grafico

La celda TIMEFRAME muestra `<grafico> / <tu orden>`. Si la primera parte no es
la del chip activo de PO, todo lo que depende de `tfSec` se degrada:

- el archivo de velas se redondea a una rejilla equivocada y **deja de crecer**
  (escaneos distintos caen en el mismo hueco y se sobrescriben);
- el contexto MTF y el backtest se calculan sobre esa serie falsa;
- la cuenta atras EJEC apunta al cierre de una vela que no existe.

Sintoma facil de ver: el contador `Archivo: N velas` se queda clavado en el
mismo numero escaneo tras escaneo.

Hasta v4.4.2 la deteccion barria **todo el texto de la pagina** buscando el
primer token tipo `M30`, y `S10` ni siquiera estaba en `TF_SECONDS`. En un
grafico S10 se leia `M30` (1800s en vez de 10s). Desde v4.4.3 se busca el
**chip activo** junto al selector de par — elemento pequeno, arriba a la
izquierda del grafico, texto exactamente un timeframe, preferido el que tiene
fondo pintado — y el barrido de texto queda solo como ultimo recurso.

Para comprobarlo desde la consola:

```js
POScannerPRO.Panel.findTimeframe()   // debe devolver lo que marca el chip
POScannerPRO.Panel.getTfSec()        // segundos correspondientes
```

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

En v4.4.1 la funcion se reescribio. Acepta ahora un digito animado envuelto
en un span hijo, el fondo pintado hasta 4 niveles por encima, la coma decimal
y toda la mitad derecha de la pantalla (antes 55%-95%), y entre varios
candidatos se queda con el **mas a la derecha** — el del eje de precio — en
vez de con el ultimo que apareciera en el DOM.

Lo que **no** cambia: se sigue exigiendo el fondo pintado. Sin el no hay forma
de distinguir el precio actual de una etiqueta fija del eje, y devolver una
fija seria peor que devolver `null`: mediria siempre lo mismo y todas las
senales saldrian EMPATE.

Si aun asi devuelve `null`, `diagPrice()` dice en cual de los tres filtros se
cae, y con esa salida se puede afinar el selector.

### Los tres metodos, en orden (v4.4.2)

La linea de estado del panel termina ahora en `| precio: <metodo> <valor>`:

1. **`eje`** — la etiqueta resaltada del eje derecho, leida directamente.
2. **`escala`** — si esa etiqueta no aparece, se calibra el eje con sus
   **etiquetas fijas**: cada una es un par (pixel Y, precio), y con tres o mas
   se ajusta por minimos cuadrados la recta `precio = a*y + b`. Con ella se
   traduce el pixel de cierre de la ultima vela a un precio real. La escala de
   un grafico es lineal por construccion, asi que el ajuste es exacto salvo el
   redondeo de las etiquetas. Se exige `R2 >= 0.995` y pendiente negativa (en
   pantalla, bajar de Y = subir de precio); si no cumple devuelve `null` en vez
   de un numero inventado.
3. **`archivo`** — ultimo recurso: comparar cierres en pixeles del archivo.
   **No es un precio**, por eso el panel no imprime numero. Es el metodo que
   producia los empates de mas.

Un cuarto metodo que se descarto: leer el estado interno de Pocket Option
(`window.__store__` y similares). Los content scripts de Chrome corren en un
**mundo aislado** y no ven las variables JS de la pagina; haria falta un
script en mundo MAIN declarado en el manifest y conocer la estructura interna
de PO. Sin poder verificar que el numero encontrado es el precio, alimentar
con el el WIN/LOSS seria repetir el bug que esta version arregla.

### Las senales antiguas no se pueden recalcular

Las senales guardadas antes de este arreglo se juzgaron comparando pixeles del
archivo. El precio real de aquellos momentos **no existe en ninguna parte** —
PO no lo expone hacia atras — asi que no hay forma de saber cuantos de aquellos
EMPATE fueron en realidad WIN o LOSS. Al cargar el historial, esas entradas se
marcan `refMethod: 'legacy'` y quedan **fuera** de `byQuality`, `byTag` y
`backtests()`; se reportan aparte para que se vea cuantas son y cuantas
empataron. A partir de aqui las estadisticas miden limpio.

Los empates no desapareceran del todo: con una binaria de 30s el precio a veces
cierra exactamente en el de entrada y PO devuelve la apuesta. Con precios
reales de cinco decimales pasan a ser raros, no cero.

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

### v4.4.5

La celda ACIERTO mostraba `0% (0W/0L/2E)` cuando ninguna senal se habia
resuelto todavia: se lee como "las pierde todas" y en realidad no habia
decidido ninguna (los EMPATE no deciden). `stats()` devuelve ahora `acc: null`
y `decididas` con el numero de WIN+LOSS; el panel muestra `sin cerrar` hasta
que haya al menos una.

### v4.4.4

- El lector ya no funde las velas con las medias moviles (ver el diagnostico
  de "Sin velas suficientes"). `CANDLE.LINE_RATIO` nuevo, `MAX_WIDTH_PX` de 30
  a 60.
- `test/boot.js`: arranque de la extension completa con DOM simulado.
- `test/pixels.js`: seis graficos sinteticos con y sin medias moviles, con el
  grafico reducido, ampliado y muy ampliado, mas un boton verde que no debe
  confundirse con una vela.

### v4.4.3

- `TF_SECONDS` gana los timeframes cortos de PO que faltaban (S1, S2, S3,
  **S10**, M2, M10, M20, H2, W1). Sin `S10` un grafico de 10 segundos se leia
  como M30.
- `findTimeframe()` ancla la deteccion al chip activo del grafico en vez de
  barrer todo el texto de la pagina.
- La linea de estado ya distingue el bloqueo por confluencia del bloqueo por
  contra-estructura (decia "contra estructura" en ambos casos).
- El mensaje del bloqueo por confluencia cita `rawScore`, el mismo numero que
  muestra el marcador, en vez del score ya penalizado.

### v4.4.2

- Segundo metodo de precio: `axisScale()`, `priceFromY()` y
  `priceFromCandle()` calibran el eje y traducen pixeles a precio real.
  `injector.js` encadena los tres metodos y el estado dice cual uso.
- `history.js`: las senales medidas con el metodo viejo se marcan `legacy` al
  cargar y salen de las estadisticas; se reportan aparte.
- `FILTER.MIN_CONFLUENCIA` baja de 7 a **6** (y de 6 a **5** para el setup
  perfecto): una senal de 6/12 como la de AUD/CHF vuelve a poder desbloquearse.
- `PERFECT.BACKTEST_MIN_ACC` baja de 65% a **55%** y `BACKTEST_MIN_N` de 10 a
  **5**, para que la condicion del backtest se pueda cumplir pronto.

### v4.4.1

`findCurrentPrice()` reescrito (ver la seccion de diagnostico) mas
`priceCandidates()` y `diagPrice()` expuestos para depurar desde la consola.
El arnes cubre la seleccion con un DOM simulado: nueve casos, incluidos los
tres que la version anterior fallaba (fondo en el padre, digito animado en un
hijo, y elegir la etiqueta correcta entre varias).

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
