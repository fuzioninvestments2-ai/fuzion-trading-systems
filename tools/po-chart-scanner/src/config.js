// ============================================================
// config.js - PO Chart Scanner PRO v4.3 CONTRARIAN ANTI-MANIPULACION
// Configuracion avanzada + persistencia en localStorage.
// NAMESPACE PROPIO: window.POScannerPRO (no choca con v2.0.4)
// v3.5.2 PERFILADA: evaluacion WIN/LOSS honesta, AUTO tras el
//   cierre, piso de calidad, anti-cuenta-regresiva, MTF sintetico.
// v3.5.3 PRECISION: tramos verticales (inmune a indicadores PO).
// v3.5.5 RECTIFICADA: lector de tramo mas largo + bandas.
// v3.5.6 COLOR REAL: verde LIMA de las velas PO + archivo sin
//   duplicados.
// v4.0 TIEMPO REAL (fin del DESFASE, verificado en video 8):
//   - MOTOR CONTINUO: foto silenciosa cada ~2.5s. La serie de
//     velas y TODOS los indicadores quedan PRE-CALCULADOS.
//   - AVISO PREVIO 5s ANTES del cierre ("PREPARATE CALL/PUT")
//     y SENAL INSTANTANEA al cerrar (+0.8s): entras con los
//     30s COMPLETOS de tu orden (antes la senal salia 3-10s
//     tarde y la entrada quedaba desfasada).
//   - CADENA NUEVA: si la lectura se rompe cerca del borde en
//     vivo, gana el tramo que llega a la ULTIMA vela (antes
//     ganaba el tramo mas largo y el analisis se anclaba atras).
//   - OVERLAY NEUTRO (cian/amarillo): las lineas del bot ya no
//     contaminan la foto (no hay que ocultarlas = sin parpadeo
//     y lectura continua posible).
// v4.1 FILTRO ESTRUCTURAL (videos 10-12: el bot daba CALL 97%
//   con el precio cayendo): la votacion mide impulso local; la
//   nueva capa STRUCT techa la senal que va contra tendencia
//   fuerte / S-R / MTF (60/55/45), con excepcion de ruptura
//   confirmada. Panel amarillo de advertencia.
// v4.2 BLOQUEO INTELIGENTE (video P1 del usuario):
//   - BLOQUEO TOTAL: la senal techada ya NO se muestra como
//     entrada. Panel = ESPERAR, overlay sin flecha, historial
//     no la registra. Antes se mostraba CALL 55 y el usuario
//     la podia tomar igual.
//   - REGLA DE LOS 90: un 90+ exige confluencia 5+ Y un aliado
//     estructural (tendencia/S-R/patron/MTF a favor). Si falta,
//     se queda en 89 (buena, no impecable).
//   - SCORE ESTABLE: se puntua SOLO con velas CERRADAS; la vela
//     en formacion hacia saltar el score en cada foto.
//   - BACKTEST MADURO: el % se muestra solo con 30+ senales de
//     muestra (BT_MIN_SHOW); antes decia "100% en 4 senales".
// v4.3 CONTRARIAN ANTI-MANIPULACION (doctorado OTC del usuario):
//   - TRAP INDEX: % de velas con mechas largas (barrido de stops).
//   - FAKEOUT en S/R: mecha pincha el nivel y cierra dentro =
//     ruptura falsa. A favor = bonus CONTRARIAN; en contra =
//     castigo (y con masa obvia = BLOQUEO total).
//   - MASA OBVIA: senal con confluencia 6+ en nivel claro = la
//     que todos ven (y el broker tambien): penalizada.
//   - ORDER FLOW inferido por RANGO de vela (proxy honesto: el
//     bot lee pixeles, NO hay volumen real en la pantalla).
//   - Historial etiquetado CONTRARIAN/NORMAL + obvia (crowd
//     loss rate real con muestra).
// v4.3.1 FIX (videos del usuario): los avisos contrarian ya NO
//   se mezclan en warning (una senal CONTRARIAN buena salia
//   etiquetada "CONTRA-ESTRUCTURA - Riesgo Alto"); y las
//   senales ya bloqueadas no reciben castigos dobles.
// v4.4.0 OPTIMIZACION DE SCORING Y FILTRADO:
//   - SETUP CONTRARIAN PERFECTO: si se cumplen las 6 condiciones
//     del doctorado (nivel x3+, fakeout, contrarian, confluencia
//     8/12, backtest contrarian >65% con muestra, trap <70%) el
//     score recibe +15 y un piso de 90. El panel dice que
//     condicion falta cuando no llega.
//   - UMBRAL DE CONFLUENCIA: menos de 7/12 fuentes = BLOQUEADA
//     (6/12 si el setup contrarian es perfecto).
//   - ETIQUETA DE ACCION por rango de score: OPERAR / OPERAR SI
//     CONTRARIAN / RIESGO MEDIO / NO OPERAR / BLOQUEADO. Debajo
//     de ENTRY_MIN el grafico NO dibuja flecha de entrada.
//   - BACKTEST SEPARADO: contrarian / normal / total.
//   OJO: subir el score de un setup no lo hace mas acertado.
//   Lo que cambia el resultado es operar menos y mejor: mide
//   el backtest CONTRARIAN antes de dar por buena la mejora.
// v4.4.1 PRECIO REAL: findCurrentPrice() se reescribe. En vivo
//   devolvia null (el panel decia "precio: archivo") y todo el
//   WIN/LOSS se juzgaba en pixeles del archivo, con EMPATE para
//   cualquier movimiento < 0.5 px: de ahi los empates de mas.
//   Ahora acepta el digito animado en un span hijo, el fondo
//   pintado en el padre, la coma decimal y toda la mitad
//   derecha de la pantalla; y elige la etiqueta MAS A LA
//   DERECHA en vez de la ultima del DOM. Diagnostico desde la
//   consola: POScannerPRO.Panel.diagPrice()
// v4.4.4 LECTOR: las MEDIAS MOVILES de PO son roja y verde lima
//   (los colores de las velas) y son CONTINUAS. En el hueco
//   entre dos velas lo unico coloreado es la media, del mismo
//   color y a la misma altura, asi que el agrupador la tomaba
//   por continuacion y pegaba vela con vela hasta pasarse de
//   MAX_WIDTH_PX; el bloque entero se descartaba. Con el
//   grafico AMPLIADO se comia casi toda la lectura: el usuario
//   vio "captura: 4 velas / 17513 px". Ahora una columna mucho
//   mas baja que la vela en curso corta el grupo, los restos de
//   linea se separan por altura y MAX_WIDTH_PX sube a 60.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('config');

POScannerPRO.CONFIG = {
  VERSION: '4.4.4',

  // --- Deteccion de color de velas (HSV, robusto a temas) ---
  // v3.5.6: verde LIMA real de las velas PO (medido en video:
  // cuerpo solido h~105-120; la Media Movil lima es h~85-95
  // y QUEDA FUERA a proposito).
  COLOR: {
    GREEN: { hMin: 100, hMax: 175, sMin: 0.40, vMin: 0.30 },  // lima PO
    RED:   { hMin: 335, hMax: 360, sMin: 0.50, vMin: 0.40 },  // rojo PO
    RED2:  { hMin: 0,   hMax: 15,  sMin: 0.50, vMin: 0.40 }
  },

  // --- Geometria de velas ---
  CANDLE: {
    MIN_WIDTH_PX: 2,
    // v4.4.4: 30px se quedaba corto con el grafico AMPLIADO (pocas
    // velas muy anchas). Los botones BUY/SELL rondan los 110px, asi
    // que 60 sigue dejandolos fuera.
    MAX_WIDTH_PX: 60,
    MIN_HEIGHT_PX: 2,
    MAX_GAP_PX: 2,
    RUN_GAP_PX: 2,      // hueco max dentro de un tramo vertical
    BODY_DENSITY: 0.6,  // % de columnas ocupadas para considerar "cuerpo" (vs mecha)
    // v4.4.4: una columna cuyo tramo mide menos de este % de la
    // altura de la vela que se esta leyendo NO es parte de ella:
    // es la MEDIA MOVIL cruzando el hueco entre vela y vela.
    LINE_RATIO: 0.35
  },

  // --- Duracion en segundos de cada timeframe de PO ---
  // v4.4.3: faltaban S10, M2, M10, M20, H2... PO los ofrece y sin
  // ellos el timeframe se leia mal (un grafico S10 se detectaba
  // como M30 al caer al primer token que hubiera en la pagina).
  TF_SECONDS: { S1:1, S2:2, S3:3, S5:5, S10:10, S15:15, S30:30,
                M1:60, M2:120, M3:180, M5:300, M10:600, M15:900,
                M20:1200, M30:1800, H1:3600, H2:7200, H4:14400,
                D1:86400, W1:604800 },

  // --- Umbrales de senal (ajustables por el usuario) ---
  SCAN: {
    MIN_CANDLES: 15,      // cantidad minima de velas para analizar
    SCORE_MIN_SIGNAL: 65, // por debajo -> NO CONFIRMADO
    SCORE_HIGH: 85,       // por encima -> Calidad HIGH
    AUTO_INTERVAL_MS: 60000, // (legado v3.5.1; v3.5.2 usa cierre+retraso)
    CAPTURE_HIDE_MS: 60,  // anti-parpadeo: pausa minima antes de la foto
    AUTO_AFTER_CLOSE_S: 1,   // (legado v3.5.2-3.5.6)
    AUTO_WINDOW_S: 8,        // (legado v3.5.2-3.5.6)
    // --- v4.0 TIEMPO REAL ---
    PRE_ALERT_S: 5,          // aviso "PREPARATE" 5s ANTES del cierre
    FINAL_AFTER_CLOSE_S: 0.8,// senal FINAL instantanea al cerrar
    CONTINUOUS_BG_MS: 2500,  // foto silenciosa de fondo (serie fresca)
    WEAK_MIN: 18,            // v3.5.4: piso absoluto de velas para registrar
    WEAK_RATIO: 0.55,        // y al menos el 55% de la MEDIANA de las
                             // ultimas 12 lecturas (piso adaptativo v3.5.4)
    SCORE_IMPECCABLE: 90     // v4.2: 90+ solo con alineacion total
  },

  // --- Historial (v3.5.2: evaluacion honesta) ---
  HISTORY: {
    GRACE_MS: 300000    // si no hay precio confiable en 5 min -> SIN DATO
  },

  // --- v4.1 FILTRO ESTRUCTURAL (techos de seguridad) ---
  // La votacion mide IMPULSO local; estos techos castigan la
  // senal que va CONTRA la estructura del mercado. Bajalos si
  // quieres un bot aun mas conservador, subelos para mas riesgo.
  STRUCT: {
    CAP_COUNTER_TREND: 60,   // contra tendencia fuerte (>=50%)
    CAP_COUNTER_SR: 60,      // CALL bajo resistencia / PUT sobre soporte
    CAP_COUNTER_SR_STRONG: 55, // nivel con 3+ toques (mas respetado)
    CAP_COUNTER_MTF: 55,     // contra la tendencia de TFs mayores
    CAP_ALL: 45,             // las tres estructuras en contra a la vez
    BREAKOUT_CANDLES: 3      // cierres mas alla del nivel = ruptura
  },

  // --- v4.3 CONTRARIAN ANTI-MANIPULACION ---
  // Umbrales de la capa anti-trampas. Todo se calcula de la
  // GEOMETRIA de las velas (pixeles): no hay volumen real ni
  // % de traders, asi que se usan proxies honestos.
  CONTRARIAN: {
    ENABLED: true,
    TRAP_WINDOW: 10,       // velas para el Trap Index
    TRAP_WICK_RATIO: 1.0,  // mecha larga = mechas >= cuerpo*1.0
    TRAP_BLOCK: 70,        // Trap Index >= 70% = alta manipulacion
    TRAP_PENALTY: 15,      // castigo por trampa / trap alto
    FAKEOUT_BONUS: 10,     // bonus contrarian (fakeout a favor)
    OBVIO_CONFLUENCIA: 6,  // confluencia >= 6 = senal que todos ven
    OBVIO_PENALTY: 12,     // castigo por senal obvia (masa)
    MASA_BLOCK: true,      // bloquear masa obvia + trampa en contra
    FLOW_PENALTY: 8        // order flow inferido en contra
  },

  // --- v4.4 FILTRADO AUTOMATICO POR SCORE ---
  // Rangos de la etiqueta de accion que pinta el panel. Cambia
  // los numeros si quieres ser mas o menos exigente.
  FILTER: {
    OPERAR: 90,              // 90-100: OPERAR (verde brillante)
    OPERAR_CONTRARIAN: 85,   // 85-89: OPERAR SI CONTRARIAN (verde)
    RIESGO_MEDIO: 75,        // 75-84: RIESGO MEDIO (amarillo)
    NO_OPERAR: 60,           // 60-74: NO OPERAR (naranja); <60 rojo
    ENTRY_MIN: 75,           // debajo: el grafico NO dibuja entrada
    WEAK_WARN: 85,           // debajo: aviso "senal debil"
    MIN_CONFLUENCIA: 6,      // <6/12 fuentes = BLOQUEADA (v4.4.2: era 7,
                             // dejaba fuera senales validas de 6/12)
    MIN_CONFLUENCIA_PERFECTO: 5  // excepcion para contrarian perfecto
  },

  // --- v4.4 SETUP CONTRARIAN PERFECTO (regla del doctorado) ---
  // Las 6 condiciones deben cumplirse TODAS. La del backtest usa
  // el acierto real de TUS senales CONTRARIAN pasadas (history):
  // no existe un backtest por patron, y inventarlo seria mentir.
  // Pon REQUIRE_BACKTEST en false si prefieres no exigirla
  // mientras acumulas muestra.
  PERFECT: {
    ENABLED: true,
    SR_TOUCHES: 3,           // nivel del fakeout con 3+ toques
    CONFLUENCIA: 8,          // 8/12 fuentes de voto
    TRAP_MAX: 70,            // trap index por debajo de 70%
    BONUS: 15,               // puntos extra si se cumple todo
    MIN_SCORE: 90,           // y piso de 90
    REQUIRE_BACKTEST: true,  // exigir la condicion del backtest
    BACKTEST_MIN_N: 5,       // v4.4.2: muestra minima (era 10)
    BACKTEST_MIN_ACC: 55     // v4.4.2: acierto minimo % (era 65)
  },

  // --- Indicadores activos (toggles) ---
  INDICATORS: {
    RSI: true, STOCH: true, MOMENTUM: true,
    MACD: true,       // v3.4.0: MACD completo (linea/senal/histograma)
    EMA_CROSS: true,  // v3.4.0: cruce EMA 9 / SMA 10
    REVERSAL: true    // v3.4.0: detector de reversion fuerte
  },

  // --- Parametros de los nuevos indicadores ---
  STOCH: { K: 14, SLOWING: 3, D: 3 },  // Estocastico 14,3,3 (como en PO)
  CROSS: { EMA_FAST: 9, SMA_SLOW: 10 },// cruce EMA 9 / SMA 10

  // --- Archivo de velas (historial profundo propio) ---
  ARCHIVE: {
    MAX: 3000,        // velas max por activo+timeframe
    BT_WINDOW: 1200,  // backtesting: cuantas velas hacia atras
    BT_STEP: 5,       // backtesting: paso entre puntos de prueba
    BT_MIN: 80,       // minimo de velas archivadas para backtest
    BT_MIN_SHOW: 30   // v4.2: no mostrar % de backtest hasta tener
                      // 30 senales de muestra (4-5 no dicen nada)
  },

  // --- Modulos de analisis avanzado ---
  MODULES: { PATTERNS: true, SR: true, TREND: true },

  // --- Alertas ---
  ALERTS: { SOUND: true, VOLUME: 0.5 },

  // --- Comentarios sobre el grafico ---
  // TTL_MS 0 = las lineas NO se borran solas; se renuevan con cada
  // escaneo de forma ATOMICA (sin parpadeo)
  OVERLAY: { ENABLED: true, TTL_MS: 0 },

  // --- Auto-trading: SIEMPRE desactivado ---
  AUTOTRADE: { ENABLED: false }
};

// --- Trampa global de errores: muestra cualquier fallo en el panel ---
window.addEventListener('error', function(e) {
  var el = document.querySelector('#po-pro-panel [data-f="status"]');
  if (el && e && e.message) {
    var f = (e.filename || '').split('/').pop();
    el.textContent = 'ERROR: ' + e.message + ' (' + f + ':' + e.lineno + ')';
  }
});

// --- Persistencia: guardar/cargar ajustes del usuario ---
POScannerPRO.Settings = {
  KEY: 'poscanner_pro_settings_v3',
  load() {
    try {
      const raw = localStorage.getItem(this.KEY);
      if (raw) Object.assign(POScannerPRO.CONFIG.SCAN, JSON.parse(raw).SCAN || {});
    } catch (e) { /* localStorage no disponible: usar defaults */ }
  },
  save() {
    try {
      localStorage.setItem(this.KEY, JSON.stringify({ SCAN: POScannerPRO.CONFIG.SCAN }));
    } catch (e) { /* silencioso */ }
  }
};
// [PO-PRO-OK:config]
