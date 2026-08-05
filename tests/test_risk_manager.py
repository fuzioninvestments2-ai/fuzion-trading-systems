"""
tests/test_risk_manager.py
==========================
Valida `src/risk/manager.py` (gestor de riesgo advisory). SIN red.

Cubre las 5 protecciones: sizing 2%, ATR/stop dinamico, circuit breaker 5%,
tope de trades/dia/par y anti-manipulacion (spikes via guard + gaps).
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.risk.manager import RiskManager, average_true_range   # noqa: E402


def test_position_sizing_2pct() -> None:
    rm = RiskManager(capital=1000.0, risk_per_trade=0.02)
    assert rm.position_size() == 20.0            # 2% de 1000
    assert rm.position_size(500.0) == 10.0       # 2% del capital dado


def test_atr_y_stop_dinamico() -> None:
    # Serie con rango constante de 2.0 -> ATR debe tender a 2.0.
    high = np.array([12, 12, 12, 12, 12, 12], dtype=float)
    low = np.array([10, 10, 10, 10, 10, 10], dtype=float)
    close = np.array([11, 11, 11, 11, 11, 11], dtype=float)
    atr = average_true_range(high, low, close, period=3)
    assert abs(atr - 2.0) < 1e-9

    rm = RiskManager(atr_period=3, atr_stop_mult=1.5)
    # CALL: stop por debajo de la entrada; PUT: por encima. dist = 2*1.5 = 3.
    assert rm.stop_loss_dinamico(11.0, "CALL", high, low, close) == 8.0
    assert rm.stop_loss_dinamico(11.0, "PUT", high, low, close) == 14.0

    # Sin datos suficientes -> None (no inventa stop).
    assert rm.stop_loss_dinamico(11.0, "CALL", [1.0], [1.0], [1.0]) is None


def test_circuit_breaker_5pct() -> None:
    rm = RiskManager(capital=1000.0, max_daily_drawdown=0.05)
    ok, _ = rm.circuit_breaker()
    assert ok is True

    # Perdida del 6% desde el pico -> corta.
    rm.registrar_trade("EURUSD_otc", -60.0)      # equity 940, pico 1000 -> dd 6%
    ok, motivo = rm.circuit_breaker()
    assert ok is False and "circuit breaker" in motivo

    # Tras reset del dia, vuelve a permitir.
    rm.reset_dia()
    assert rm.circuit_breaker()[0] is True


def test_tope_trades_por_par() -> None:
    rm = RiskManager(max_trades_por_par=2)
    par = "GBPUSD_otc"
    assert rm.puede_operar(par)[0] is True
    rm.registrar_trade(par, +1.0)
    rm.registrar_trade(par, +1.0)               # ya 2 en el par
    ok, motivo = rm.puede_operar(par)
    assert ok is False and "tope" in motivo
    # Otro par no se ve afectado.
    assert rm.puede_operar("EURUSD_otc")[0] is True


def test_anti_manipulacion_gap() -> None:
    rm = RiskManager(gap_umbral_pct=0.004)
    # Serie plana con un GAP del ~1% en medio.
    normal = list(np.linspace(1.1000, 1.1002, 40))
    con_gap = normal[:20] + [1.1150] + normal[20:]
    limpio, razones = rm.anti_manipulacion(con_gap)
    assert limpio is False and any("gap" in r for r in razones)

    # Serie suave sin anomalias -> limpia.
    limpio2, razones2 = rm.anti_manipulacion(normal)
    assert limpio2 is True and razones2 == []


def test_puede_operar_integrado() -> None:
    rm = RiskManager(capital=1000.0, max_daily_drawdown=0.05, max_trades_por_par=3)
    par = "EURUSD_otc"
    serie = list(np.linspace(1.1000, 1.1005, 40))
    ok, motivo = rm.puede_operar(par, prices=serie)
    assert ok is True and motivo == "ok"

    # Fuerza circuit breaker: gana primero (sube el pico) y luego cae fuerte.
    rm.registrar_trade(par, -60.0)
    assert rm.puede_operar(par, prices=serie)[0] is False


def _run_all() -> None:
    tests = [test_position_sizing_2pct, test_atr_y_stop_dinamico,
             test_circuit_breaker_5pct, test_tope_trades_por_par,
             test_anti_manipulacion_gap, test_puede_operar_integrado]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
