"""
bot/test_engine.py
==================
Prueba de validación del motor base (Regla 4): config + velas + estrategia.

Verifica:
  (A) Config: presets válidos y derivación de votos/confianza; validación falla
      ante parámetros absurdos.
  (B) Velas: los ticks se agrupan en OHLC correctamente.
  (C) Estrategia: devuelve una señal válida y una estructura coherente.
  (D) End-to-end: ticks -> velas -> estrategia sin errores.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.config import TradingConfig, get_preset, STACK_METHODS
from bot.candles import CandleBuilder
from bot.scoring_strategy import ScoringStrategy, CALL, PUT, HOLD


def test_config():
    # Los presets deben construirse sin error y derivar votos/confianza.
    for name in ("conservador", "moderado", "agresivo"):
        cfg = get_preset(name)
        params = STACK_METHODS[cfg.stack_method]
        assert cfg.required_votes == params["required_votes"]
        assert cfg.min_confidence == params["min_confidence"]

    # Un parámetro absurdo debe fallar pronto y claro.
    try:
        TradingConfig(trade_capital=-5)
        raise AssertionError("❌ Debía rechazar capital negativo")
    except ValueError:
        pass
    print("✅ (A) Config: presets y validación correctos.")


def test_candles():
    cb = CandleBuilder(timeframe_seconds=60)   # velas de 1 min
    base = 0
    # Intervalo 0 (ms 0..59999): 10, 12, 9, 11 -> O10 H12 L9 C11 vol4
    for p, t in [(10, 0), (12, 15_000), (9, 30_000), (11, 45_000)]:
        closed = cb.add_tick(p, base + t)
        assert closed is None, "❌ No debía cerrar vela dentro del mismo minuto"
    # Primer tick del minuto siguiente -> cierra la vela anterior.
    closed = cb.add_tick(13, 60_000)
    assert closed is not None, "❌ Debía cerrar la vela al cambiar de minuto"
    assert closed["open"] == 10 and closed["high"] == 12
    assert closed["low"] == 9 and closed["close"] == 11
    assert closed["volume"] == 4, f"❌ volume(ticks) esperado 4, dio {closed['volume']}"
    print("✅ (B) Velas: OHLC agregado correctamente.")


def test_strategy_estructura():
    cfg = get_preset("moderado")
    strat = ScoringStrategy(cfg)

    # Construimos velas a partir de una tendencia bajista fuerte + rebote,
    # solo para comprobar que la salida es coherente (no medimos rentabilidad).
    cb = CandleBuilder(60)
    price = 100.0
    ts = 0
    for i in range(300):
        # baja 250 velas y sube 50 (para mover RSI/estocástico).
        price += -0.2 if i < 250 else 0.4
        cb.add_tick(price, ts)
        ts += 60_000            # un tick por minuto -> una vela por tick
    df = cb.to_dataframe()

    signal, confidence, details = strat.analyze(df)
    assert signal in (CALL, PUT, HOLD), f"❌ Señal inválida: {signal}"
    assert 0.0 <= confidence <= 1.0, f"❌ Confianza fuera de rango: {confidence}"
    assert "votes" in details
    print(f"✅ (C) Estrategia: señal={signal}, confianza={confidence:.2f}")
    print("     votos:", details["votes"])


def test_end_to_end():
    cfg = get_preset("agresivo")
    strat = ScoringStrategy(cfg)
    cb = CandleBuilder(cfg.timeframe_seconds())

    rng = random.Random(123)
    price = 100.0
    ts = 0
    señales = {CALL: 0, PUT: 0, HOLD: 0}
    for i in range(1000):
        price += rng.uniform(-0.5, 0.5)          # paseo aleatorio
        closed = cb.add_tick(price, ts)
        ts += 20_000                              # 3 ticks por vela M1
        if closed is not None:                    # al cerrar vela, analizamos
            sig, _, _ = strat.analyze(cb.to_dataframe())
            señales[sig] += 1
    total = sum(señales.values())
    assert total > 0, "❌ No se analizó ninguna vela cerrada"
    print(f"✅ (D) End-to-end OK. Análisis por vela: {señales}")


if __name__ == "__main__":
    test_config()
    test_candles()
    test_strategy_estructura()
    test_end_to_end()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
