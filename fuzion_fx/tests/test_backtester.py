"""
tests/test_backtester.py (fuzion_fx)
====================================
Valida el backtester: resolucion win/loss fiel, sin mirar el futuro, y que
aflojar umbrales sube la frecuencia. SIN red (velas sinteticas deterministas).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Sequence

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.backtester import backtest_series, combinar   # noqa: E402
from core.signal_engine import SignalEngine, CALL, PUT, NEUTRAL   # noqa: E402

_IND = {"ema_fast": 9, "ema_slow": 21, "rsi_period": 14, "macd_fast": 12,
        "macd_slow": 26, "macd_signal": 9, "bb_period": 20, "bb_std": 2.0,
        "atr_period": 14}
_SIG = {"min_confirmations": 3}


class _FakeCall(SignalEngine):
    """Siempre CALL (para aislar la resolucion win/loss del calculo de indicadores)."""
    def analyze(self, candles):
        close = list(candles["close"])
        return {"signal": CALL, "confirmations": 3, "votes": {},
                "confirming": ["ema", "macd", "rsi"], "setup_id": "CALL|ema,macd,rsi",
                "atr": 0.0, "price": close[-1], "readings": {}}


def _serie(vals):
    c = list(vals)
    return {"open": c, "high": c, "low": c, "close": c}


def test_resolucion_call_en_alza_todo_wins() -> None:
    # Serie estrictamente creciente + engine que siempre da CALL: cada salida
    # (close[i+1]) > entrada (close[i]) -> TODO wins, cero losses/ties.
    serie = _serie(np.linspace(1.1000, 1.1100, 40))
    r = backtest_series(serie, _IND, _SIG, 60, warmup=25, engine=_FakeCall(_IND, _SIG))
    assert r["losses"] == 0 and r["ties"] == 0
    assert r["wins"] == r["emissions"] > 0
    assert r["win_pct"] == 100.0


def test_resolucion_call_en_baja_todo_losses() -> None:
    # Serie decreciente + CALL siempre: cada salida < entrada -> TODO losses.
    serie = _serie(np.linspace(1.1100, 1.1000, 40))
    r = backtest_series(serie, _IND, _SIG, 60, warmup=25, engine=_FakeCall(_IND, _SIG))
    assert r["wins"] == 0 and r["losses"] == r["emissions"] > 0
    assert r["win_pct"] == 0.0


def test_empate_no_cuenta_en_winrate() -> None:
    # Serie plana + CALL siempre: salida == entrada -> todo ties, win_pct None.
    serie = _serie([1.1000] * 40)
    r = backtest_series(serie, _IND, _SIG, 60, warmup=25, engine=_FakeCall(_IND, _SIG))
    assert r["wins"] == 0 and r["losses"] == 0
    assert r["ties"] == r["emissions"] > 0 and r["win_pct"] is None


def test_sin_mirar_el_futuro() -> None:
    # Cambiar SOLO la ultima vela no altera ningun resultado: la ultima no se
    # resuelve (no tiene 'siguiente') y nunca entra como [0..i] de una emision.
    base = list(np.linspace(1.1000, 1.1100, 40))
    r1 = backtest_series(_serie(base), _IND, _SIG, 60, warmup=25,
                         engine=_FakeCall(_IND, _SIG))
    alterada = base[:-1] + [9.9999]            # ultima vela absurda
    r2 = backtest_series(_serie(alterada), _IND, _SIG, 60, warmup=25,
                         engine=_FakeCall(_IND, _SIG))
    assert r1["wins"] == r2["wins"] and r1["losses"] == r2["losses"]
    assert r1["emissions"] == r2["emissions"]


def test_aflojar_rsi_sube_frecuencia() -> None:
    # Oscilante con leve sesgo: con RSI 45/55 el motor emite MAS que con 30/70.
    rng = 1.10 + np.cumsum(np.array([-0.0002, 0.00015] * 60))
    serie = _serie(rng)
    estricto = backtest_series(serie, _IND, _SIG, 60)
    ind_suelto = {**_IND, "rsi_oversold": 45, "rsi_overbought": 55}
    suelto = backtest_series(serie, ind_suelto, _SIG, 60)
    assert suelto["emissions"] >= estricto["emissions"]
    assert suelto["signals_per_hour"] >= estricto["signals_per_hour"]


def test_combinar_agrega_bien() -> None:
    a = {"readings": 100, "emissions": 10, "wins": 6, "losses": 4, "ties": 0,
         "win_pct": 60.0, "emission_rate": 0.1, "signals_per_hour": 6.0}
    b = {"readings": 100, "emissions": 20, "wins": 8, "losses": 12, "ties": 0,
         "win_pct": 40.0, "emission_rate": 0.2, "signals_per_hour": 12.0}
    c = combinar([a, b])
    assert c["wins"] == 14 and c["losses"] == 16 and c["pares"] == 2
    assert c["win_pct"] == round(14 / 30 * 100, 1)     # global sobre resueltos
    assert c["signals_per_hour"] == 9.0                # promedio por par


def _run_all() -> None:
    tests = [test_resolucion_call_en_alza_todo_wins,
             test_resolucion_call_en_baja_todo_losses,
             test_empate_no_cuenta_en_winrate,
             test_sin_mirar_el_futuro,
             test_aflojar_rsi_sube_frecuencia,
             test_combinar_agrega_bien]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
