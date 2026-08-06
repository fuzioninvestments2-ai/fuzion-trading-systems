"""
tests/test_risk_manager.py (fuzion_fx)
======================================
Valida RiskManager: sizing, circuit breaker diario, recovery por par y tope de
trades/dia. SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.risk_manager import RiskManager                       # noqa: E402

_RISK = {"max_daily_trades_per_pair": 3, "max_daily_loss_pct": 5.0,
         "recovery_after_consecutive_losses": 2, "news_buffer_minutes": 5,
         "default_stake_pct": 1.0}


def test_position_size() -> None:
    rm = RiskManager(_RISK, capital=1000.0)
    assert rm.position_size() == 10.0            # 1% de 1000


def test_circuit_breaker_diario() -> None:
    rm = RiskManager(_RISK, capital=1000.0)
    assert rm.circuit_breaker()[0] is True
    rm.register_result("EUR/USD", -60.0, won=False)   # -6% > 5% -> corta
    ok, motivo = rm.circuit_breaker()
    assert ok is False and "circuit breaker" in motivo
    # can_trade tambien queda bloqueado para cualquier par.
    assert rm.can_trade("GBP/USD")[0] is False


def test_recovery_por_par() -> None:
    rm = RiskManager(_RISK, capital=1000.0)
    par = "EUR/USD"
    rm.register_result(par, -5.0, won=False)
    assert rm.in_recovery(par) is False          # 1 perdida, aun no
    rm.register_result(par, -5.0, won=False)
    assert rm.in_recovery(par) is True           # 2 seguidas -> recovery
    assert rm.can_trade(par)[0] is False         # pausado
    # Otro par no se ve afectado.
    assert rm.can_trade("USD/JPY")[0] is True
    # Una ganadora saca del recovery.
    rm.register_result(par, +8.0, won=True)
    assert rm.in_recovery(par) is False


def test_tope_trades_por_par() -> None:
    rm = RiskManager(_RISK, capital=100000.0)    # capital alto: no dispara breaker
    par = "GBP/JPY"
    for _ in range(3):
        assert rm.can_trade(par)[0] is True
        rm.register_result(par, +1.0, won=True)
    assert rm.can_trade(par)[0] is False         # 3 alcanzado
    assert "tope" in rm.can_trade(par)[1]


def test_reset_day() -> None:
    rm = RiskManager(_RISK, capital=1000.0)
    rm.register_result("EUR/USD", -60.0, won=False)
    rm.reset_day()
    assert rm.circuit_breaker()[0] is True
    assert rm.can_trade("EUR/USD")[0] is True


def _run_all() -> None:
    tests = [test_position_size, test_circuit_breaker_diario, test_recovery_por_par,
             test_tope_trades_por_par, test_reset_day]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
