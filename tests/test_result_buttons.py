"""
tests/test_result_buttons.py
============================
Valida `src/telegram/result_buttons.py` (reporte manual + enrutado unico). SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.core.trading_system import FuzionTradingSystem          # noqa: E402
from src.risk.manager import RiskManager                         # noqa: E402
from src.telegram import result_buttons as rb                    # noqa: E402


def test_row_y_parse_ida_y_vuelta() -> None:
    fila = rb.result_buttons_row("EURUSD_otc", 92)
    labels = [l for l, _ in fila]
    assert labels == ["✅ Gané", "❌ Perdí", "➖ No entré"]
    info = rb.parse_result_callback(fila[0][1])
    assert info == {"outcome": "win", "pair": "EURUSD_otc", "payout": 92.0}


def test_parse_invalidos() -> None:
    assert rb.parse_result_callback("analyze") is None
    assert rb.parse_result_callback("res:win:EURUSD_otc") is None       # faltan campos
    assert rb.parse_result_callback("res:xxx:EURUSD_otc:92") is None    # outcome malo
    assert rb.parse_result_callback("res:win::92") is None              # sin par
    assert rb.parse_result_callback("res:win:EURUSD_otc:abc") is None   # payout no numerico


def test_user_pnl() -> None:
    assert rb.user_pnl("win", 100.0, 92) == 92.0        # +stake*payout%
    assert rb.user_pnl("loss", 100.0, 92) == -100.0     # -stake
    assert rb.user_pnl("skip", 100.0, 92) == 0.0        # no entro
    assert rb.user_pnl("win", 50.0, 0.8) == 40.0        # payout en fraccion


def test_route_win_alimenta_riesgo() -> None:
    rm = RiskManager(); rm.set_capital(10000.0)          # position_size -> 200
    system = FuzionTradingSystem(risk_manager=rm)
    rec = rb.route_user_result(system, "res:loss:EURUSD_otc:92")
    assert rec["source"] == "user" and rec["traded"] is True
    assert rec["pnl"] == -200.0
    assert rm.is_in_recovery_mode("EURUSD_otc") is True  # perdida real -> recovery


def test_route_skip_no_toca_riesgo() -> None:
    rm = RiskManager(); rm.set_capital(10000.0)
    system = FuzionTradingSystem(risk_manager=rm)
    rec = rb.route_user_result(system, "res:skip:EURUSD_otc:92")
    assert rec["traded"] is False and rec["pnl"] == 0.0
    assert rm.equity == 10000.0                          # capital intacto
    assert rm.is_in_recovery_mode("EURUSD_otc") is False
    # Igual queda en analytics (memoria).
    assert system.signal_results[-1]["source"] == "user"


def test_route_stake_explicito_y_callback_invalido() -> None:
    rm = RiskManager(); rm.set_capital(10000.0)
    system = FuzionTradingSystem(risk_manager=rm)
    rec = rb.route_user_result(system, "res:win:GBPUSD_otc:85", stake=10.0)
    assert rec["pnl"] == 8.5 and rec["stake"] == 10.0    # 10 * 85%
    assert rb.route_user_result(system, "analyze") is None


def _run_all() -> None:
    tests = [test_row_y_parse_ida_y_vuelta, test_parse_invalidos, test_user_pnl,
             test_route_win_alimenta_riesgo, test_route_skip_no_toca_riesgo,
             test_route_stake_explicito_y_callback_invalido]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
