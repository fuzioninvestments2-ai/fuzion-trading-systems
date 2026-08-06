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


def test_traded_results_since() -> None:
    store = ResultsStore(_FakeRepo())
    # ts viejos (ayer) y de hoy; solo traded=1 debe volver, en orden.
    store.save_result({"signal_id": "a", "pair": "EURUSD_otc", "outcome": "loss",
                       "pnl": -50.0, "stake": 50.0, "traded": True, "source": "user",
                       "ts": 1000})
    store.save_result({"signal_id": "b", "pair": "EURUSD_otc", "outcome": "skip",
                       "pnl": 0.0, "stake": 0.0, "traded": False, "source": "user",
                       "ts": 5000})
    store.save_result({"signal_id": "c", "pair": "GBPUSD_otc", "outcome": "win",
                       "pnl": 80.0, "stake": 100.0, "traded": True, "source": "user",
                       "ts": 5000})
    hoy = store.traded_results_since(2000)
    assert [r["signal_id"] if "signal_id" in r else r["pair"] for r in hoy] == ["GBPUSD_otc"]
    assert hoy[0]["pnl"] == 80.0                 # el skip y el viejo quedan fuera


def test_restore_state_reconstruye_dia() -> None:
    repo = _FakeRepo()
    store = ResultsStore(repo)
    # Historial del dia: -100 (EUR), +85 (GBP), -50 (EUR) -> pnl_hoy = -65.
    for sid, par, pnl in [("s1", "EURUSD_otc", -100.0), ("s2", "GBPUSD_otc", 85.0),
                          ("s3", "EURUSD_otc", -50.0)]:
        store.save_result({"signal_id": sid, "pair": par, "outcome": "loss",
                           "pnl": pnl, "stake": 100.0, "traded": True,
                           "source": "user", "ts": 10_000})

    # Reinicio: balance real actual = 9935 (= 10000 + (-65)).
    rm = RiskManager()
    system = FuzionTradingSystem(risk_manager=rm, db=store)
    n = system.restore_state(since_ts=1, current_balance=9935.0)
    assert n == 3
    # Equity reconstruido == balance real (sin doble conteo).
    assert rm.equity == 9935.0
    # Base del dia = 10000; pico = 10000 (nunca subio por encima del inicio).
    assert rm.peak_equity == 10000.0
    # Drawdown = (10000-9935)/10000 = 0.65% -> circuit breaker NO corta.
    assert rm.circuit_breaker()[0] is True
    # Recovery: EUR cerro en perdida -> ON; GBP cerro en ganancia -> OFF.
    assert rm.is_in_recovery_mode("EURUSD_otc") is True
    assert rm.is_in_recovery_mode("GBPUSD_otc") is False
    # Tope por par reconstruido: 2 trades en EUR, 1 en GBP.
    assert rm.trades_por_par == {"EURUSD_otc": 2, "GBPUSD_otc": 1}


def test_restore_state_dispara_circuit_breaker() -> None:
    repo = _FakeRepo()
    store = ResultsStore(repo)
    # Perdida fuerte del dia: -600 sobre 10000 (>5%).
    store.save_result({"signal_id": "s1", "pair": "EURUSD_otc", "outcome": "loss",
                       "pnl": -600.0, "stake": 600.0, "traded": True,
                       "source": "user", "ts": 10_000})
    rm = RiskManager()
    system = FuzionTradingSystem(risk_manager=rm, db=store)
    system.restore_state(since_ts=1, current_balance=9400.0)
    # Tras el reinicio, el circuit breaker sigue cortado (proteccion preservada).
    ok, motivo = rm.circuit_breaker()
    assert ok is False and "circuit breaker" in motivo


def _run_all() -> None:
    tests = [test_save_y_recent, test_integrado_con_trading_system,
             test_persiste_tras_recrear_store, test_traded_results_since,
             test_restore_state_reconstruye_dia,
             test_restore_state_dispara_circuit_breaker]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
