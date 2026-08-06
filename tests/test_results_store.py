"""
tests/test_results_store.py
===========================
Valida `src/core/results_store.py` (persistencia user performance) integrado con
FuzionTradingSystem. SIN red: usa sqlite en memoria.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.core.results_store import ResultsStore                  # noqa: E402
from src.core.trading_system import FuzionTradingSystem          # noqa: E402
from src.risk.manager import RiskManager                         # noqa: E402


class _FakeRepo:
    """Repo minimo compatible: conn sqlite en memoria + lock (como HistoryRepository)."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self._lock = threading.Lock()


def test_save_y_recent() -> None:
    store = ResultsStore(_FakeRepo())
    store.save_result({"signal_id": "s1", "pair": "EURUSD_otc", "outcome": "loss",
                       "pnl": -200.0, "stake": 200.0, "traded": True, "source": "user"})
    store.save_result({"signal_id": "s2", "pair": "EURUSD_otc", "outcome": "skip",
                       "pnl": 0.0, "stake": 0.0, "traded": False, "source": "user"})
    todos = store.recent()
    assert len(todos) == 2 and todos[0]["signal_id"] == "s2"      # mas nuevo primero
    solo_par = store.recent(pair="EURUSD_otc")
    assert len(solo_par) == 2
    # PnL realizado: solo cuenta el trade operado (-200), no el skip.
    assert store.realized_pnl("EURUSD_otc") == -200.0


def test_integrado_con_trading_system() -> None:
    store = ResultsStore(_FakeRepo())
    rm = RiskManager(); rm.set_capital(10000.0)
    system = FuzionTradingSystem(risk_manager=rm, db=store)
    # Usuario opero y perdio: alimenta riesgo Y persiste.
    system.on_user_reported_result("s10", "EURUSD_otc", user_won=False,
                                   user_stake=100.0, user_pnl=-100.0)
    # No entro: NO toca riesgo pero SI persiste (analytics).
    system.on_user_reported_result("s11", "EURUSD_otc", user_won=False,
                                   user_stake=0.0, user_pnl=0.0)
    guardados = store.recent(pair="EURUSD_otc")
    assert len(guardados) == 2
    assert store.realized_pnl() == -100.0
    assert rm.is_in_recovery_mode("EURUSD_otc") is True


def test_persiste_tras_recrear_store() -> None:
    # Mismo repo/conexion: un ResultsStore nuevo ve lo que guardo el anterior
    # (persistencia real, no memoria del objeto).
    repo = _FakeRepo()
    s1 = ResultsStore(repo)
    s1.save_result({"signal_id": "x", "pair": "GBPUSD_otc", "outcome": "win",
                    "pnl": 85.0, "stake": 100.0, "traded": True, "source": "user"})
    s2 = ResultsStore(repo)                                       # reabre el schema
    assert s2.realized_pnl("GBPUSD_otc") == 85.0


def _run_all() -> None:
    tests = [test_save_y_recent, test_integrado_con_trading_system,
             test_persiste_tras_recrear_store]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
