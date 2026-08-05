"""
tests/test_result_buttons.py
============================
Valida `src/telegram/result_buttons.py` (reporte manual del usuario). SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src.risk.manager import RiskManager                     # noqa: E402
from src.telegram import result_buttons as rb                # noqa: E402


def test_row_y_parse_ida_y_vuelta() -> None:
    fila = rb.result_buttons_row("EURUSD_otc", 92)
    labels = [l for l, _ in fila]
    assert labels == ["✅ Gané", "❌ Perdí", "➖ Empate"]
    # El callback de "Gané" se parsea de vuelta a sus partes.
    data_win = fila[0][1]
    info = rb.parse_result_callback(data_win)
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
    assert rb.user_pnl("tie", 100.0, 92) == 0.0
    # payout en fraccion 0.8 equivale a 80%.
    assert rb.user_pnl("win", 50.0, 0.8) == 40.0


def test_apply_user_result_afecta_recovery() -> None:
    rm = RiskManager()
    rm.set_capital(10000.0)                              # position_size -> 200
    par = "EURUSD_otc"
    # Perdida reportada -> registrar_trade(par, -200) -> recovery ON.
    res = rb.apply_user_result(rm, f"res:loss:{par}:92")
    assert res["pnl"] == -200.0 and res["stake"] == 200.0
    assert rm.is_in_recovery_mode(par) is True
    # Ganancia reportada -> limpia recovery.
    rb.apply_user_result(rm, f"res:win:{par}:92")
    assert rm.is_in_recovery_mode(par) is False
    # Callback invalido -> None, sin efecto.
    assert rb.apply_user_result(rm, "analyze") is None


def test_apply_stake_explicito() -> None:
    rm = RiskManager()
    rm.set_capital(10000.0)
    res = rb.apply_user_result(rm, "res:win:GBPUSD_otc:85", stake=10.0)
    assert res["pnl"] == 8.5 and res["stake"] == 10.0    # 10 * 85%


def _run_all() -> None:
    tests = [test_row_y_parse_ida_y_vuelta, test_parse_invalidos, test_user_pnl,
             test_apply_user_result_afecta_recovery, test_apply_stake_explicito]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
