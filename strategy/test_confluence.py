"""
strategy/test_confluence.py
===========================
Prueba de validación de la estrategia de confluencia (Regla 4).

Probamos sobre todo la FUNCIÓN PURA `evaluate_signal` (determinista, inyectando
valores), y hacemos un smoke-test del streaming y del backtest.

HONESTIDAD: estas pruebas verifican que la LÓGICA dispara correctamente, NO que
la estrategia gane dinero. El win-rate del backtest es solo descriptivo de los
datos sintéticos usados.
"""

import os
import sys

# Permitir importar el paquete del proyecto (indicators/, strategy/) al ejecutar
# este archivo directamente, sin depender del directorio de trabajo.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
from strategy.confluence import (
    StrategyConfig, evaluate_signal, ConfluenceStrategy, backtest,
    CALL, PUT, NONE,
)


def test_call_por_sobreventa():
    cfg = StrategyConfig()
    # RSI en sobreventa (25) + estocástico cruzando al alza desde zona baja.
    # antes: %K(10) <= %D(15) ; ahora: %K(18) > %D(12) -> cruce al alza.
    s = evaluate_signal(price=100, ema=None, rsi=25, k=18, d=12,
                        prev_k=10, prev_d=15, cfg=cfg)
    assert s == CALL, f"❌ Se esperaba CALL, se obtuvo {s}"
    print("✅ (A) CALL por sobreventa + cruce al alza.")


def test_put_por_sobrecompra():
    cfg = StrategyConfig()
    # RSI en sobrecompra (75) + cruce a la baja desde zona alta.
    # antes: %K(90) >= %D(85) ; ahora: %K(82) < %D(88) -> cruce a la baja.
    s = evaluate_signal(price=100, ema=None, rsi=75, k=82, d=88,
                        prev_k=90, prev_d=85, cfg=cfg)
    assert s == PUT, f"❌ Se esperaba PUT, se obtuvo {s}"
    print("✅ (B) PUT por sobrecompra + cruce a la baja.")


def test_none_sin_confluencia():
    cfg = StrategyConfig()
    # RSI en sobreventa pero SIN cruce (sigue %K por debajo) -> no operar.
    s = evaluate_signal(price=100, ema=None, rsi=25, k=10, d=15,
                        prev_k=8, prev_d=12, cfg=cfg)
    assert s == NONE, f"❌ Se esperaba NONE, se obtuvo {s}"
    # Datos insuficientes (algún None) -> NONE prudente.
    s2 = evaluate_signal(price=100, ema=None, rsi=None, k=None, d=None,
                         prev_k=None, prev_d=None, cfg=cfg)
    assert s2 == NONE, f"❌ Con datos None se esperaba NONE, se obtuvo {s2}"
    print("✅ (C) Sin confluencia / sin datos -> NONE.")


def test_filtro_tendencia():
    # Con filtro activado, un CALL válido se ANULA si el precio está por debajo
    # de la EMA (tendencia bajista fuerte): el filtro hace su trabajo.
    cfg = StrategyConfig(use_trend_filter=True)
    s = evaluate_signal(price=90, ema=100, rsi=25, k=18, d=12,
                        prev_k=10, prev_d=15, cfg=cfg)
    assert s == NONE, f"❌ El filtro debía anular el CALL, se obtuvo {s}"
    # Sin el filtro, el mismo caso SÍ daría CALL (control).
    cfg2 = StrategyConfig(use_trend_filter=False)
    s2 = evaluate_signal(price=90, ema=100, rsi=25, k=18, d=12,
                         prev_k=10, prev_d=15, cfg=cfg2)
    assert s2 == CALL, f"❌ Sin filtro debía dar CALL, se obtuvo {s2}"
    print("✅ (D) Filtro de tendencia EMA anula/permite según corresponde.")


def test_backtest_estructura():
    # Serie oscilante sintética para que la estrategia tenga oportunidades.
    t = np.arange(300)
    precios = 100 + 5 * np.sin(t / 5.0)        # onda suave
    res = backtest(precios, expiry_horizon=3)

    # Coherencia interna de los conteos (no medimos rentabilidad).
    assert res["wins"] + res["losses"] + res["ties"] == res["total_signals"], \
        "❌ Los conteos del backtest no cuadran"
    assert res["total_signals"] >= 0
    if res["win_rate"] is not None:
        assert 0.0 <= res["win_rate"] <= 1.0
    print("✅ (E) Backtest devuelve estructura coherente:")
    print("    ", res)


if __name__ == "__main__":
    test_call_por_sobreventa()
    test_put_por_sobrecompra()
    test_none_sin_confluencia()
    test_filtro_tendencia()
    test_backtest_estructura()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
