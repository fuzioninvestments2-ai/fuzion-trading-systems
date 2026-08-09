"""
tests/test_result_card.py (fuzion_fx)
=====================================
Valida SignalCardFormatter.format_result: iconos WIN/LOSS/EMPATE, nota de
recuperacion SOLO en LOSS, precios FX a 5 decimales y disclaimer. Puro, SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from telegram.signal_formatter import SignalCardFormatter    # noqa: E402


def _base(**over):
    d = {"bot_name": "Fuzion F1 (1M)", "pair": "EUR/USD", "card_label": "1M",
         "result": "win", "direction": "CALL", "entry": 1.10345, "exit": 1.10410}
    d.update(over)
    return d


def test_icono_win() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(result="win"))
    assert "✅ WIN" in txt


def test_icono_loss_con_recuperacion() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(result="loss"))
    assert "❌ LOSS" in txt
    # La nota de recuperacion aparece SOLO en LOSS.
    assert "RECUPERACION" in txt
    assert "no se dobla" in txt


def test_icono_empate() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(result="tie"))
    assert "➖ EMPATE" in txt


def test_win_no_lleva_recuperacion() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(result="win"))
    assert "RECUPERACION" not in txt


def test_precios_cinco_decimales() -> None:
    fmt = SignalCardFormatter()
    # Entra un precio con menos decimales -> se muestra a 5.
    txt = fmt.format_result(_base(entry=1.1, exit=1.10009))
    assert "1.10000" in txt
    assert "1.10009" in txt


def test_disclaimer_resultado() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base())
    assert "Demo · resultado educativo · el acierto no esta garantizado" in txt


def _run_all() -> None:
    tests = [test_icono_win, test_icono_loss_con_recuperacion, test_icono_empate,
             test_win_no_lleva_recuperacion, test_precios_cinco_decimales,
             test_disclaimer_resultado]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
