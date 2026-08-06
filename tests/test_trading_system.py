"""
tests/test_trading_system.py
============================
Valida `src/core/trading_system.py` (orquestador). SIN red.

Clave: el flujo auto (signal performance) NO toca el RiskManager; el flujo user
SOLO lo toca si user_stake > 0. Persistencia via db inyectada (fake).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.core.trading_system import FuzionTradingSystem, calculate_pnl  # noqa: E402
from src.risk.manager import RiskManager                                # noqa: E402


class _FakeDB:
    """DB de prueba: registra llamadas, sin red."""
    def __init__(self, pares=None):
        self.saved = []
        self.pares = pares or {}

    def save_signal_result(self, signal_id, pnl, source):
        self.saved.append((signal_id, pnl, source))

    def get_signal_pair(self, signal_id):
        return self.pares.get(signal_id, "")


def test_calculate_pnl() -> None:
    assert calculate_pnl(1.10, 1.11, "CALL")[0] == "win"
    assert calculate_pnl(1.10, 1.09, "CALL")[0] == "loss"
    assert calculate_pnl(1.10, 1.09, "PUT")[0] == "win"
    assert calculate_pnl(1.10, 1.10, "CALL") == ("tie", 0.0)


def test_signal_expired_no_toca_riesgo() -> None:
    db = _FakeDB()
    sys_ = FuzionTradingSystem(db=db)
    equity_antes = sys_.risk_manager.equity
    rec = sys_.on_signal_expired("sig1", 1.10, 1.12, "CALL")
    # Auto: se registra en analytics y db, pero el RiskManager queda intacto.
    assert rec["source"] == "auto" and rec["outcome"] == "win"
    assert sys_.risk_manager.equity == equity_antes
    assert db.saved == [("sig1", rec["pnl"], "auto")]


def test_user_result_opero_alimenta_riesgo() -> None:
    db = _FakeDB(pares={"sig2": "EURUSD_otc"})
    rm = RiskManager(); rm.set_capital(10000.0)
    sys_ = FuzionTradingSystem(risk_manager=rm, db=db)
    # Usuario OPERO y perdio -50: alimenta el gestor (recovery ON) y persiste user.
    rec = sys_.on_user_reported_result("sig2", pair="", user_won=False,
                                       user_stake=50.0, user_pnl=-50.0)
    assert rec["traded"] is True and rec["pair"] == "EURUSD_otc"   # pair resuelto de db
    assert rm.is_in_recovery_mode("EURUSD_otc") is True
    assert rm.equity == 9950.0
    assert ("sig2", -50.0, "user") in db.saved


def test_user_result_no_opero_no_toca_riesgo() -> None:
    rm = RiskManager(); rm.set_capital(10000.0)
    sys_ = FuzionTradingSystem(risk_manager=rm)
    # Usuario NO opero (stake 0): NO debe tocar el RiskManager.
    rec = sys_.on_user_reported_result("sig3", pair="GBPUSD_otc", user_won=False,
                                       user_stake=0.0, user_pnl=0.0)
    assert rec["traded"] is False
    assert rm.is_in_recovery_mode("GBPUSD_otc") is False
    assert rm.equity == 10000.0                                   # intacto


def _run_all() -> None:
    tests = [test_calculate_pnl, test_signal_expired_no_toca_riesgo,
             test_user_result_opero_alimenta_riesgo,
             test_user_result_no_opero_no_toca_riesgo]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
