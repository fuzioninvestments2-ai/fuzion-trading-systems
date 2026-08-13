"""
core/backtester.py (fuzion_fx)
==============================
Replica el motor sobre velas historicas y mide su rendimiento REAL, sin mirar el
futuro: en cada vela `i` analiza SOLO las velas [0..i] (como en vivo) y resuelve
el resultado con el cierre de la vela siguiente `i+1` (horizonte = 1 vela del
timeframe), IGUAL que `base_bot.resolve_pending`:

    entrada = close[i]          salida = close[i+1]
    CALL gana si salida > entrada;  PUT gana si salida < entrada;  empate si igual.

PORQUE: para calibrar umbrales (RSI/Bollinger/confirmaciones) hay que medir el
acierto y la frecuencia sobre datos reales, no a ojo. El empate se EXCLUYE del
win-rate (como el aprendizaje, que no registra ties). Metrica cruda por par: no
aplica anti-duplicado ni tope/hora (esos son filtros de entrega, aguas abajo);
mide la calidad del motor en si.

Sin red. Se prueba con velas sinteticas deterministas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.signal_engine import SignalEngine, NEUTRAL
from core.multi_timeframe import MultiTimeframeAnalyzer, MIN_VELAS


def _warmup_minimo(ind: Dict[str, Any]) -> int:
    """Velas minimas antes de la primera lectura para que los indicadores esten
    formados (la ventana mas larga entre todos + 1)."""
    return max(
        int(ind.get("ema_slow", 21)),
        int(ind.get("macd_slow", 26)) + int(ind.get("macd_signal", 9)),
        int(ind.get("bb_period", 20)),
        int(ind.get("rsi_period", 14)) + 1,
        int(ind.get("atr_period", 14)) + 1,
    ) + 1


def backtest_series(candles: Dict[str, Sequence[float]],
                    indicators_cfg: Dict[str, Any],
                    signal_cfg: Dict[str, Any],
                    timeframe_seconds: int,
                    warmup: Optional[int] = None,
                    engine: Optional[SignalEngine] = None) -> Dict[str, Any]:
    """
    Corre el motor vela a vela sobre UNA serie (un par) y devuelve las metricas:

        {readings, emissions, wins, losses, ties, win_pct, emission_rate,
         signals_per_hour, by_setup}

    - readings: ventanas evaluadas (una por vela tras el warmup).
    - emissions: lecturas que dieron CALL/PUT.
    - win_pct: wins / (wins+losses) * 100  (empates excluidos). None sin muestra.
    - signals_per_hour: tasa CRUDA por par = emission_rate * (3600/timeframe_seconds).
      No incluye anti-duplicado ni tope/hora (filtros de entrega, aguas abajo).
    - by_setup: {setup_id: {trades, wins, win_pct}} para ver que jugada rinde.
    """
    close = list(candles["close"])
    n = len(close)
    # engine inyectable para tests (fake determinista); por defecto el real.
    eng = engine if engine is not None else SignalEngine(indicators_cfg, signal_cfg)
    warmup = _warmup_minimo(indicators_cfg) if warmup is None else int(warmup)

    readings = emissions = wins = losses = ties = 0
    by_setup: Dict[str, Dict[str, int]] = {}

    # Hasta n-1 exclusivo: la ultima vela no tiene 'siguiente' para resolver.
    for i in range(max(warmup, 1), n - 1):
        sub = {k: list(v)[: i + 1] for k, v in candles.items()
               if k in ("open", "high", "low", "close")}
        readings += 1
        res = eng.analyze(sub)
        if res["signal"] == NEUTRAL:
            continue

        emissions += 1
        entrada = close[i]
        salida = close[i + 1]
        if salida == entrada:
            ties += 1
            continue
        gano = (salida > entrada) if res["signal"] == "CALL" else (salida < entrada)
        if gano:
            wins += 1
        else:
            losses += 1

        sid = res["setup_id"]
        b = by_setup.setdefault(sid, {"trades": 0, "wins": 0})
        b["trades"] += 1                       # trades = resueltos (sin empates)
        if gano:
            b["wins"] += 1

    resueltos = wins + losses
    win_pct = round(wins / resueltos * 100, 1) if resueltos else None
    emission_rate = round(emissions / readings, 4) if readings else 0.0
    sph = round(emission_rate * (3600.0 / timeframe_seconds), 2) if timeframe_seconds else 0.0

    for sid, b in by_setup.items():
        b["win_pct"] = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None

    return {
        "readings": readings,
        "emissions": emissions,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": win_pct,
        "emission_rate": emission_rate,
        "signals_per_hour": sph,
        "by_setup": by_setup,
    }


# =====================================================================
# BACKTEST MULTI-TEMPORALIDAD (la "formula de tiempo" + patrones + fuerza)
# =====================================================================
# Convencion de tiempos relativa a la serie BASE (la mas fina). El backtest
# resamplea la base a los tiempos mas largos y corre la convergencia como en vivo.
_FACTORES = {60: 1, 120: 2, 180: 3, 300: 5, 600: 10, 900: 15, 1800: 30, 3600: 60}


def resample(candles: Dict[str, Sequence[float]], factor: int
             ) -> Dict[str, List[float]]:
    """
    Agrega la serie base a una mas gruesa (cada `factor` velas -> una). open=primer,
    high=max, low=min, close=ultimo. Solo velas COMPLETAS (descarta la cola parcial).
    """
    o = list(candles["open"]); h = list(candles["high"])
    lo = list(candles["low"]); c = list(candles["close"])
    n = len(c) - (len(c) % factor)
    out = {"open": [], "high": [], "low": [], "close": []}
    for i in range(0, n, factor):
        out["open"].append(o[i])
        out["high"].append(max(h[i:i + factor]))
        out["low"].append(min(lo[i:i + factor]))
        out["close"].append(c[i + factor - 1])
    return out


def backtest_convergencia(base_candles: Dict[str, Sequence[float]],
                          base_tf_seconds: int, indicators_cfg: Dict[str, Any],
                          signal_cfg: Dict[str, Any], *, umbral: float = 0.35,
                          min_tf: int = 3, min_fuerza: float = 0.0,
                          politica: str = "no_contradice") -> Dict[str, Any]:
    """
    Backtest de la FOTO COMPLETA sobre UNA serie base (la mas fina, ej. 1m), SIN
    mirar el futuro: en cada vela i arma la foto multi-temporalidad con las velas
    [0..i] de la base y sus resampleos, decide con el motor de una tf + la
    convergencia (misma politica/fuerza que en vivo) y resuelve con close[i+1].

    Devuelve {emissions, wins, losses, ties, win_pct, by_fuerza:{fuertes,debiles},
    emission_rate}. by_fuerza separa acierto de señales FUERTES (fuerza>=0.45) vs
    DEBILES para PROBAR si la confluencia alta rinde mas.
    """
    close = list(base_candles["close"])
    n = len(close)
    eng = SignalEngine(indicators_cfg, signal_cfg)
    mtf = MultiTimeframeAnalyzer(indicators_cfg, umbral)
    warmup = _warmup_minimo(indicators_cfg)

    # Resampleos por tiempo (relativos a la base). tf base incluido (factor 1).
    resamp: Dict[int, Dict[str, List[float]]] = {}
    for tf, fac in _FACTORES.items():
        tf_seg = base_tf_seconds * fac
        resamp[tf_seg] = base_candles if fac == 1 else resample(base_candles, fac)

    emissions = wins = losses = ties = 0
    fu = {"fuertes": {"trades": 0, "wins": 0}, "debiles": {"trades": 0, "wins": 0}}

    for i in range(max(warmup, MIN_VELAS), n - 1):
        sub = {k: list(base_candles[k])[: i + 1]
               for k in ("open", "high", "low", "close")}
        res = eng.analyze(sub)
        if res["signal"] == NEUTRAL:
            continue

        # Foto: cada tiempo con SUS velas completas hasta la base i.
        velas_por_tf: Dict[int, Any] = {}
        for tf_seg, serie in resamp.items():
            fac = tf_seg // base_tf_seconds
            k = (i + 1) // fac                    # velas completas de ese tf hasta i
            if k >= 2:
                velas_por_tf[tf_seg] = {c2: serie[c2][:k] for c2 in
                                        ("open", "high", "low", "close")}
        conv = mtf.analizar(velas_por_tf)
        sig = conv["signal"]
        apoya = sig == res["signal"]
        opuesta = sig != NEUTRAL and not apoya
        if politica == "confirma":
            if not (apoya and conv["total"] >= min_tf):
                continue
        elif politica == "no_contradice":
            if opuesta:
                continue
        fuerza = conv["convergencia"] if apoya else 0.0
        if min_fuerza > 0 and fuerza < min_fuerza:
            continue

        entrada = close[i]; salida = close[i + 1]
        emissions += 1
        if salida == entrada:
            ties += 1
            continue
        gano = (salida > entrada) if res["signal"] == "CALL" else (salida < entrada)
        banda = "fuertes" if fuerza >= 0.45 else "debiles"
        fu[banda]["trades"] += 1
        if gano:
            wins += 1; fu[banda]["wins"] += 1
        else:
            losses += 1

    resueltos = wins + losses
    for b in fu.values():
        b["win_pct"] = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None
    readings = max(n - 1 - max(warmup, MIN_VELAS), 0)
    return {
        "emissions": emissions, "wins": wins, "losses": losses, "ties": ties,
        "win_pct": round(wins / resueltos * 100, 1) if resueltos else None,
        "emission_rate": round(emissions / readings, 4) if readings else 0.0,
        "by_fuerza": fu,
    }


def combinar(resultados: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Agrega los resultados de varios pares en una sola metrica (para calibrar sobre
    los 22 pares juntos). Suma conteos; el win_pct global es sobre el total de
    resueltos; signals_per_hour se promedia por par (tasa cruda por par).
    """
    if not resultados:
        return {"readings": 0, "emissions": 0, "wins": 0, "losses": 0, "ties": 0,
                "win_pct": None, "emission_rate": 0.0, "signals_per_hour": 0.0,
                "pares": 0}
    readings = sum(r["readings"] for r in resultados)
    emissions = sum(r["emissions"] for r in resultados)
    wins = sum(r["wins"] for r in resultados)
    losses = sum(r["losses"] for r in resultados)
    ties = sum(r["ties"] for r in resultados)
    resueltos = wins + losses
    win_pct = round(wins / resueltos * 100, 1) if resueltos else None
    emission_rate = round(emissions / readings, 4) if readings else 0.0
    # Promedio de la tasa por par (cada par tiene su propia serie/tiempo cubierto).
    sph = round(sum(r["signals_per_hour"] for r in resultados) / len(resultados), 2)
    return {
        "readings": readings,
        "emissions": emissions,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": win_pct,
        "emission_rate": emission_rate,
        "signals_per_hour": sph,
        "pares": len(resultados),
    }
