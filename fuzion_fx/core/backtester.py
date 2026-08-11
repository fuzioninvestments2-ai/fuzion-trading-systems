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
