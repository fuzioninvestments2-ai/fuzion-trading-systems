// ============================================================
// scoring.js - PRO v4.3.0 CONTRARIAN ANTI-MANIPULACION
// Score 0-100 por votacion ponderada + CONFLUENCIA:
//   12 fuentes de voto: RSI, Estocastico(nivel), Estocastico
//   14,3,3(cruce %K/%D), Momentum, MACD(histograma), MACD(cruce),
//   cruce EMA9/SMA10, estructura de color, patrones, S/R,
//   tendencia y CONTEXTO MULTI-TIMEFRAME (historial archivado
//   de TFs mayores = menos ruido, mas probabilidad).
//   BONUS por confluencia (>=3:+5, >=4:+10, >=5:+15).
// v3.4.0: DETECTOR DE REVERSION FUERTE (alcista/bajista): si 3+
// condiciones de giro coinciden, suma como fuente extra con peso
// doble y lo anuncia en detail.reversion.
// v4.1.0: FILTRO ESTRUCTURAL (casco anti contra-tendencia).
//   El motor vota igual que siempre, pero al final una capa de
//   ESTRUCTURA DE MERCADO revisa la senal ganadora:
//     - CONTRA TENDENCIA fuerte (strength>=50) -> techo 60
//     - CONTRA S/R (CALL en resistencia / PUT en soporte)
//       -> techo 60 (55 si el nivel tiene 3+ toques)
//     - CONTRA contexto MTF (archivo de TFs mayores) -> techo 55
//     - Las TRES a la vez -> techo 45
//   EXCEPCION: ruptura confirmada del nivel (3 velas cerrando
//   mas alla) anula el techo de S/R. El techo baja la calidad
//   y suele apagar la confirmacion (<65): la senal PELIGROSA se
//   muestra con advertencia amarilla y NO entra al historial.
// v4.3.0: CAPA CONTRARIAN ANTI-MANIPULACION (doctorado OTC):
//   tras el filtro estructural, ContrarianScoring ajusta el
//   score segun trampas del broker (Trap Index por mechas,
//   fakeouts en S/R, reversal ratio), masa obvia (senal que
//   todos ven) y order flow inferido (proxy por rango, el bot
//   lee pixeles: NO hay volumen real). Fakeout A FAVOR = bonus
//   CONTRARIAN; masa obvia CON trampa en contra = BLOQUEO.
// ============================================================
window.POScannerPRO = window.POScannerPRO || {};
POScannerPRO._mods = POScannerPRO._mods || [];
POScannerPRO._mods.push('scoring');

POScannerPRO.Scoring = (() => {
  const CFG = POScannerPRO.CONFIG;

  function evaluate(candles, ctx) {
    const P = POScannerPRO;
    const I = P.Indicators;
    const T = CFG.INDICATORS;
    const M = CFG.MODULES;
    const rsi = I.rsi(candles);
    const stochF = I.stochasticFull(candles, CFG.STOCH.K, CFG.STOCH.SLOWING, CFG.STOCH.D);
    const stoch = stochF.k;                    // %K suavizado (nivel)
    const mom = I.momentum(candles);
    const mf = T.MACD ? I.macdFull(candles) : null;
    const macd = mf ? mf.hist : I.macd(candles); // histograma (o simple)
    const cross = T.EMA_CROSS ?
      I.emaSmaCross(candles, CFG.CROSS.EMA_FAST, CFG.CROSS.SMA_SLOW) :
      { state: 'FLAT', crossed: null };
    const v = I.votes(candles);

    let callPts = 0, putPts = 0;
    // Fuentes que votaron a cada lado (para la confluencia)
    let callSrc = 0, putSrc = 0;

    // --- 1) RSI: sobreventa -> rebote CALL / sobrecompra -> PUT ---
    if (T.RSI) {
      if (rsi < 30) { callPts += 2; callSrc++; }
      else if (rsi > 70) { putPts += 2; putSrc++; }
      else if (rsi < 45) { callPts += 1; callSrc++; }
      else if (rsi > 55) { putPts += 1; putSrc++; }
    }
    // --- 2) Estocastico NIVEL: zona de sobreventa/sobrecompra ---
    if (T.STOCH) {
      if (stoch < 20) { callPts += 2; callSrc++; }
      else if (stoch > 80) { putPts += 2; putSrc++; }
    }
    // --- 3) Estocastico CRUCE %K/%D (14,3,3): giro temprano ---
    if (T.STOCH) {
      const upX = stochF.prevK <= stochF.prevD && stochF.k > stochF.d;
      const dnX = stochF.prevK >= stochF.prevD && stochF.k < stochF.d;
      if (upX && stochF.k < 30) { callPts += 2; callSrc++; }      // cruce en sobreventa
      else if (dnX && stochF.k > 70) { putPts += 2; putSrc++; }   // cruce en sobrecompra
      else if (stochF.k > stochF.d) { callPts += 1; callSrc++; }  // %K sobre %D
      else if (stochF.k < stochF.d) { putPts += 1; putSrc++; }
    }
    // --- 4) Momentum: signo directo ---
    if (T.MOMENTUM) {
      if (mom > 0) { callPts += 2; callSrc++; }
      else if (mom < 0) { putPts += 2; putSrc++; }
    }
    // --- 5) MACD HISTOGRAMA: direccion y giro del momentum ---
    if (T.MACD && mf) {
      if (mf.hist > 0 && mf.rising) { callPts += 1; callSrc++; }
      else if (mf.hist < 0 && !mf.rising) { putPts += 1; putSrc++; }
      else if (mf.hist < 0 && mf.rising) { callPts += 1; callSrc++; }  // se recupera
      else if (mf.hist > 0 && !mf.rising) { putPts += 1; putSrc++; }   // se agota
    }
    // --- 6) MACD CRUCE linea/senal: senal clasica fuerte ---
    if (T.MACD && mf) {
      if (mf.crossUp) { callPts += 2; callSrc++; }
      else if (mf.crossDown) { putPts += 2; putSrc++; }
    }
    // --- 7) CRUCE EMA 9 / SMA 10 (tus medias en PO) ---
    if (T.EMA_CROSS) {
      if (cross.crossed === 'CALL') { callPts += 2; callSrc++; }
      else if (cross.crossed === 'PUT') { putPts += 2; putSrc++; }
      else if (cross.state === 'UP') { callPts += 1; callSrc++; }
      else if (cross.state === 'DOWN') { putPts += 1; putSrc++; }
    }
    // --- 8) Estructura: predominio de color en ultimas 10 velas ---
    const rv = I.votes(candles.slice(-10));
    if (rv.call > rv.put) { callPts += 1; callSrc++; }
    else if (rv.put > rv.call) { putPts += 1; putSrc++; }

    // --- 9) PATRONES de velas: cada patron con sesgo suma 2 ---
    let patterns = [];
    if (M.PATTERNS) {
      patterns = P.PatternDetector.detect(candles);
      let pc = 0, pp = 0;
      patterns.forEach(p => {
        if (p.bias > 0) { callPts += 2; pc++; }
        else if (p.bias < 0) { putPts += 2; pp++; }
      });
      if (pc) callSrc++;
      if (pp) putSrc++;
    }

    // --- 11) TENDENCIA: se calcula ANTES de S/R para el filtro anti-cuchillo
    let trend = { trend: 'FLAT', strength: 0 };
    if (M.TREND) trend = P.TrendAnalyzer.analyze(candles);
    function trendDownStrong() { return trend.trend === 'DOWN' && trend.strength >= 50; }
    function trendUpStrong()   { return trend.trend === 'UP'   && trend.strength >= 50; }
    if (M.TREND) {
      // v3.4.0: tendencia fuerte pesa DOBLE (manda sobre osciladores)
      const w = trend.strength >= 50 ? 2 : 1;
      if (trend.trend === 'UP') { callPts += w; callSrc++; }
      else if (trend.trend === 'DOWN') { putPts += w; putSrc++; }
    }

    // --- 10) SOPORTE/RESISTENCIA: rebote esperado en el nivel ---
    let sr = { near: null, levels: [] };
    if (M.SR) {
      sr = P.SupportResistance.proximity(candles);
      // v3.4.0: el rebote en S/R solo vota si NO contradice una
      // tendencia fuerte (evita "atrapar el cuchillo que cae")
      const strongDown = trendDownStrong();
      const strongUp = trendUpStrong();
      if (sr.near && sr.near.type === 'S' && !strongDown) { callPts += 2; callSrc++; }
      if (sr.near && sr.near.type === 'R' && !strongUp) { putPts += 2; putSrc++; }
    }

    // --- 12) CONTEXTO MULTI-TIMEFRAME (v3.5.0): la tendencia de
    // los TFs MAYORES archivados filtra la senal (impulso + historial)
    let contexto = { dir: 'FLAT', used: [], score: 0 };
    if (ctx && ctx.asset && ctx.tfSec && P.CandleArchive) {
      try {
        contexto = P.CandleArchive.higherTrend(ctx.asset, ctx.tfSec);
        if (contexto.dir === 'UP') { callPts += Math.abs(contexto.score) >= 2 ? 2 : 1; callSrc++; }
        else if (contexto.dir === 'DOWN') { putPts += Math.abs(contexto.score) >= 2 ? 2 : 1; putSrc++; }
      } catch (e) { /* archivo aun vacio */ }
    }

    // --- REVERSION FUERTE (v3.4.0): detector multi-condicion ---
    // Cuenta condiciones de GIRO; con 3+ la reversion es FUERTE y
    // vota con peso doble (soluciona "reversion alcista con % bajo")
    let reversion = null;
    if (T.REVERSAL) {
      const last5 = candles.slice(-5);
      const last = candles[candles.length - 1];
      const prev = candles[candles.length - 2] || last;
      const avgBody = candles.slice(-14).reduce((a, c) =>
        a + Math.abs(c.close - c.open), 0) / Math.min(14, candles.length) || 1;
      // Condiciones de REVERSION ALCISTA.
      // v3.4.0 fix: exige EVIDENCIA del giro (vela verde reciente o
      // patron alcista); sin eso, una caida larga siempre "parece"
      // reversion por RSI bajo y es falso positivo.
      const hayGiroAlcista = last.dir === 'CALL' || patterns.some(p => p.bias > 0);
      const hayGiroBajista = last.dir === 'PUT' || patterns.some(p => p.bias < 0);
      let rc = 0;
      if (trend.trend === 'DOWN' || rv.put > rv.call) rc++;              // venia cayendo
      if (patterns.some(p => p.bias > 0)) rc++;                          // patron alcista
      if (last.dir === 'CALL' && Math.abs(last.close - last.open) > avgBody * 1.5) rc++; // vela verde fuerte
      if (rsi < 40) rc++;                                                // RSI en zona baja
      if (mf && mf.hist < 0 && mf.rising) rc++;                          // MACD girando arriba
      if (stochF.prevK <= stochF.prevD && stochF.k > stochF.d && stochF.k < 35) rc++; // cruce stoch bajo
      if (cross.crossed === 'CALL') rc++;                                // cruce EMA9/SMA10
      // Condiciones de REVERSION BAJISTA (espejo)
      let rp = 0;
      if (trend.trend === 'UP' || rv.call > rv.put) rp++;
      if (patterns.some(p => p.bias < 0)) rp++;
      if (last.dir === 'PUT' && Math.abs(last.close - last.open) > avgBody * 1.5) rp++;
      if (rsi > 60) rp++;
      if (mf && mf.hist > 0 && !mf.rising) rp++;
      if (stochF.prevK >= stochF.prevD && stochF.k < stochF.d && stochF.k > 65) rp++;
      if (cross.crossed === 'PUT') rp++;
      // Vela verde tras caida (ultima CALL y anterior PUT) como giro simple
      const giroVerde = last.dir === 'CALL' && prev.dir === 'PUT';
      const giroRoja  = last.dir === 'PUT' && prev.dir === 'CALL';
      if (giroVerde) rc++;
      if (giroRoja) rp++;

      if (hayGiroAlcista) {
        if (rc >= 3) { callPts += 4; callSrc++; reversion = 'ALCISTA FUERTE'; }
        else if (rc === 2) { callPts += 2; callSrc++; reversion = 'ALCISTA (moderada)'; }
      }
      if (hayGiroBajista) {
        if (rp >= 3) { putPts += 4; putSrc++; reversion = 'BAJISTA FUERTE'; }
        else if (rp === 2) { putPts += 2; putSrc++; reversion = 'BAJISTA (moderada)'; }
      }
    }

    const dir = callPts >= putPts ? 'CALL' : 'PUT';
    const total = callPts + putPts || 1;
    const winner = Math.max(callPts, putPts);
    const base = Math.round(winner / total * 100);

    // --- CONFLUENCIA: fuentes independientes que coinciden ---
    const agree = dir === 'CALL' ? callSrc : putSrc;
    let bonus = 0;
    if (agree >= 5) bonus = 15;
    else if (agree >= 4) bonus = 10;
    else if (agree >= 3) bonus = 5;
    let score = Math.min(97, base + bonus);

    // ========================================================
    // v4.1 FILTRO ESTRUCTURAL (casco anti contra-tendencia)
    // v4.2: BLOQUEO TOTAL (blocked = ESPERAR) + REGLA DE LOS 90
    // La votacion mide el IMPULSO local; esta capa mide la
    // ESTRUCTURA (tendencia + S/R + MTF). Una senal local
    // brillante que va contra la estructura es una trampa:
    // se TECHA el score y se BLOQUEA la entrada. Y un 90+
    // exige alineacion total (confluencia + aliado claro).
    // ========================================================
    const S = CFG.STRUCT || {};
    const CAP_TREND   = S.CAP_COUNTER_TREND   != null ? S.CAP_COUNTER_TREND   : 60;
    const CAP_SR      = S.CAP_COUNTER_SR      != null ? S.CAP_COUNTER_SR      : 60;
    const CAP_SR_STR  = S.CAP_COUNTER_SR_STRONG != null ? S.CAP_COUNTER_SR_STRONG : 55;
    const CAP_MTF     = S.CAP_COUNTER_MTF     != null ? S.CAP_COUNTER_MTF     : 55;
    const CAP_ALL     = S.CAP_ALL             != null ? S.CAP_ALL             : 45;
    const BRK_N       = S.BREAKOUT_CANDLES    != null ? S.BREAKOUT_CANDLES    : 3;

    let cap = 100;
    const reasons = [];
    let ruptura = null;   // 'R' o 'S' si el nivel cercano quedo ROTO

    // 1) CONTRA TENDENCIA FUERTE (la estructura manda sobre el impulso)
    if (trend.strength >= 50) {
      if (dir === 'CALL' && trend.trend === 'DOWN') {
        cap = Math.min(cap, CAP_TREND);
        reasons.push('CONTRA-TENDENCIA (mercado BAJISTA fuerte ' + trend.strength + '%)');
      } else if (dir === 'PUT' && trend.trend === 'UP') {
        cap = Math.min(cap, CAP_TREND);
        reasons.push('CONTRA-TENDENCIA (mercado ALCISTA fuerte ' + trend.strength + '%)');
      }
    }

    // 2) CONTRA S/R: CALL bajo RESISTENCIA o PUT sobre SOPORTE.
    //    EXCEPCION: ruptura confirmada = las ultimas BRK_N velas
    //    cierran MAS ALLA del nivel (ojo: Y invertida, menor Y =
    //    precio mayor; romper R al alza = cierres con Y < nivel).
    if (sr.near) {
      const lv = sr.near;
      const lastN = candles.slice(-BRK_N);
      if (dir === 'CALL' && lv.type === 'R') {
        const rota = lastN.length === BRK_N && lastN.every(c => c.close < lv.y);
        if (rota) { ruptura = 'R'; }
        else {
          const fuerte = lv.touches >= 3;
          cap = Math.min(cap, fuerte ? CAP_SR_STR : CAP_SR);
          reasons.push('bajo RESISTENCIA x' + lv.touches + ' (sin ruptura)');
        }
      } else if (dir === 'PUT' && lv.type === 'S') {
        const roto = lastN.length === BRK_N && lastN.every(c => c.close > lv.y);
        if (roto) { ruptura = 'S'; }
        else {
          const fuerte = lv.touches >= 3;
          cap = Math.min(cap, fuerte ? CAP_SR_STR : CAP_SR);
          reasons.push('sobre SOPORTE x' + lv.touches + ' (sin ruptura)');
        }
      }
    }

    // 3) CONTRA MTF: el contexto de TFs MAYORES archivados
    //    contradice la senal. Si aun no hay archivo, NO castiga
    //    (seria injusto: el contexto se construye escaneando).
    if (contexto.used && contexto.used.length && contexto.dir !== 'FLAT') {
      if (dir === 'CALL' && contexto.dir === 'DOWN') {
        cap = Math.min(cap, CAP_MTF);
        reasons.push('contra MTF (' + contexto.used.join(' ') + ' BAJISTA)');
      } else if (dir === 'PUT' && contexto.dir === 'UP') {
        cap = Math.min(cap, CAP_MTF);
        reasons.push('contra MTF (' + contexto.used.join(' ') + ' ALCISTA)');
      }
    }

    // Las TRES estructuras en contra a la vez = trampa total
    if (reasons.length >= 3) cap = Math.min(cap, CAP_ALL);

    const rawScore = score;
    let warning = null;
    if (score > cap) {
      score = cap;
      warning = 'RIESGO ALTO: senal ' + reasons.join(' + ') +
                '. Score real ' + rawScore + ' techado a ' + cap + '.';
    }
    if (ruptura) {
      warning = (warning ? warning + ' ' : '') +
        'Ruptura de ' + (ruptura === 'R' ? 'RESISTENCIA' : 'SOPORTE') +
        ' confirmada (' + BRK_N + ' cierres mas alla): techo de S/R anulado.';
    }

    // v4.2: BLOQUEO TOTAL de la senal techada. Ya no se muestra
    // como entrada: el panel dice ESPERAR, el overlay no dibuja
    // flecha y el historial no la registra. (Un aviso de RUPTURA
    // sin techo NO bloquea: es una confirmacion, no un riesgo.)
    let blocked = (score < rawScore);
    let blockReason = blocked ? 'estructura' : null;

    // ========================================================
    // v4.3 CAPA CONTRARIAN ANTI-MANIPULACION: ajusta el score
    // segun trampas del broker (Trap Index, fakeouts), masa
    // obvia y order flow inferido. Corre DESPUES del filtro
    // estructural: nunca desbloquea una contra-estructura y
    // puede anadir un bloqueo nuevo (masa obvia + trampa).
    // ========================================================
    let contra = null;
    if (CFG.CONTRARIAN && CFG.CONTRARIAN.ENABLED !== false &&
        P.ContrarianScoring) {
      try {
        contra = P.ContrarianScoring.adjust({
          dir: dir, score: score, agree: agree, candles: candles,
          trend: trend, sr: sr, patterns: patterns, blocked: blocked
        });
        score = contra.score;
        if (contra.bloqueoMasa && !blocked) {
          blocked = true;
          blockReason = 'masa';
        }
        if (contra.lines.length) {
          warning = (warning ? warning + ' ' : '') + contra.lines.join(' | ');
        }
      } catch (e) { /* capa contrarian desactivada o incompleta */ }
    }

    // v4.2: REGLA DE LOS 90 (senal IMPECABLE). Un 90+ solo se
    // permite con TODO alineado: confluencia alta (5+ fuentes) Y
    // al menos UN aliado estructural claro (tendencia a favor,
    // S/R a favor, patron alineado o MTF a favor). Si falta, la
    // senal es buena pero no impecable: se queda en 89.
    let nota90 = null;
    const MIN90 = CFG.SCAN.SCORE_IMPECCABLE || 90;
    if (score >= MIN90) {
      const aFavorTendencia =
        (dir === 'CALL' && trend.trend === 'UP'   && trend.strength >= 25) ||
        (dir === 'PUT'  && trend.trend === 'DOWN' && trend.strength >= 25);
      const aFavorSR = sr.near &&
        ((dir === 'CALL' && sr.near.type === 'S') ||
         (dir === 'PUT'  && sr.near.type === 'R'));
      const aFavorPatron = patterns.some(p =>
        dir === 'CALL' ? p.bias > 0 : p.bias < 0);
      const aFavorMTF = !!(contexto.used && contexto.used.length) &&
        ((dir === 'CALL' && contexto.dir === 'UP') ||
         (dir === 'PUT'  && contexto.dir === 'DOWN'));
      if (agree < 5 ||
          !(aFavorTendencia || aFavorSR || aFavorPatron || aFavorMTF)) {
        score = MIN90 - 1;   // 89: buena, no impecable
        nota90 = 'Para 90+ (IMPECABLE) se exige confluencia 5+ y un ' +
                 'aliado estructural (tendencia/S-R/patron/MTF a favor). ' +
                 'Confluencia actual: ' + agree + '/12.';
      }
    }

    // Calidad segun umbrales configurables (tras el techo)
    let quality = 'LOW';
    if (score >= CFG.SCAN.SCORE_HIGH) quality = 'HIGH';
    else if (score >= CFG.SCAN.SCORE_MIN_SIGNAL) quality = 'MEDIUM';

    return {
      dir: dir, score: score, quality: quality,
      confirmed: score >= CFG.SCAN.SCORE_MIN_SIGNAL,
      warning: warning,               // v4.1: texto de alerta o null
      rawScore: rawScore,             // v4.1: score antes del techo
      blocked: blocked,               // v4.2: true = ESPERAR (no entrar)
      blockReason: blockReason,       // v4.3: 'estructura' | 'masa' | null
      contrarian: !!(contra && contra.contrarian), // v4.3: fakeout a favor
      esObvia: !!(contra && contra.esObvia),       // v4.3: senal de masa
      note: nota90,                   // v4.2: por que no llego a 90+
      detail: {
        rsi: rsi.toFixed(1),
        stoch: stoch.toFixed(1), stochD: stochF.d.toFixed(1),
        momentum: mom.toFixed(2), macd: macd.toFixed(2),
        emaCross: cross.crossed ? ('CRUCE ' + cross.crossed) :
                  (cross.state === 'UP' ? 'EMA9>SMA10' :
                   cross.state === 'DOWN' ? 'EMA9<SMA10' : 'planas'),
        reversion: reversion,
        votosCALL: callPts, votosPUT: putPts, velas: v.total,
        confluencia: agree + '/12',
        patterns: patterns.map(p => p.name),
        srNear: sr.near ? (sr.near.type === 'S' ? 'SOPORTE' : 'RESISTENCIA') : '-',
        srLevels: sr.levels.length,
        trend: trend.trend,
        trendStrength: trend.strength,
        // v4.3: metricas anti-manipulacion para el panel
        trapIndex: contra ? contra.trapIndex : null,
        reversalRatio: contra ? contra.reversalRatio : null,
        fakeout: contra ? contra.fakeout : null,
        actividad: contra ? contra.actividad : null,
        contexto: contexto.used.length
          ? (contexto.dir === 'UP' ? 'ALCISTA' : contexto.dir === 'DOWN' ? 'BAJISTA' : 'mixto') +
            ' en ' + contexto.used.join(' ')
          : 'sin datos (escanea 1 vez en M1/M5 para crearlo)'
      }
    };
  }

  // VOTACION LIGERA (v3.5.0): solo para BACKTESTING masivo del
  // CandleArchive (rapida, sin patrones ni S/R). Devuelve
  // 'CALL' | 'PUT' | null (empate = sin senal).
  function quickEvaluate(candles) {
    const I = POScannerPRO.Indicators;
    if (!candles || candles.length < 40) return null;
    const rsi = I.rsi(candles);
    const sf = I.stochasticFull(candles, 14, 3, 3);
    const mom = I.momentum(candles);
    const mf = I.macdFull(candles);
    let c = 0, p = 0;
    if (rsi < 35) c += 2; else if (rsi > 65) p += 2;
    if (sf.prevK <= sf.prevD && sf.k > sf.d) c++;
    else if (sf.prevK >= sf.prevD && sf.k < sf.d) p++;
    if (mom > 0) c++; else if (mom < 0) p++;
    if (mf) { if (mf.hist > 0) c++; else if (mf.hist < 0) p++; }
    const rv = I.votes(candles.slice(-10));
    if (rv.call > rv.put) c++; else if (rv.put > rv.call) p++;
    if (c === p) return null;
    return c > p ? 'CALL' : 'PUT';
  }

  return { evaluate: evaluate, quickEvaluate: quickEvaluate };
})();
// [PO-PRO-OK:scoring]
