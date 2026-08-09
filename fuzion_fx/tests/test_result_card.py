"""
tests/test_result_card.py (fuzion_fx)
=====================================
Valida SignalCardFormatter.format_result: iconos WIN/LOSS/EMPATE, nota de
recuperacion SOLO si modo_recuperacion=True (booleano explicito del bot),
precios FX a 5 decimales y disclaimer. Puro, SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from telegram.signal_formatter import SignalCardFormatter    # noqa: E402


def _base(**over):
    d = {"bot_name": "Fuzion FX 1M", "par": "EUR/USD", "card_label": "1M",
         "resultado": "win", "direccion": "CALL", "entrada": 1.10345,
         "cierre": 1.10410, "modo_recuperacion": False}
    d.update(over)
    return d


def test_icono_win() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(resultado="win"))
    assert "✅ WIN" in txt


def test_icono_loss() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(resultado="loss"))
    assert "❌ LOSS" in txt


def test_icono_empate() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(resultado="tie"))
    assert "➖ EMPATE" in txt


def test_recuperacion_solo_con_flag() -> None:
    fmt = SignalCardFormatter()
    # La nota depende del booleano explicito, no de que sea LOSS.
    con = fmt.format_result(_base(resultado="loss", modo_recuperacion=True))
    assert "RECUPERACION" in con
    assert "no se dobla" in con


def test_loss_sin_flag_no_lleva_recuperacion() -> None:
    fmt = SignalCardFormatter()
    # LOSS pero el par NO entra en recuperacion -> sin nota.
    txt = fmt.format_result(_base(resultado="loss", modo_recuperacion=False))
    assert "RECUPERACION" not in txt


def test_win_no_lleva_recuperacion() -> None:
    # Caso normal: WIN no entra en recuperacion (el bot no marca el flag).
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base(resultado="win", modo_recuperacion=False))
    assert "RECUPERACION" not in txt


def test_precios_cinco_decimales() -> None:
    fmt = SignalCardFormatter()
    # Entra un precio con menos decimales -> se muestra a 5.
    txt = fmt.format_result(_base(entrada=1.1, cierre=1.10009))
    assert "1.10000" in txt
    assert "1.10009" in txt


def test_disclaimer_resultado() -> None:
    fmt = SignalCardFormatter()
    txt = fmt.format_result(_base())
    assert "Demo · resultado educativo · el acierto no esta garantizado" in txt


def _run_all() -> None:
    tests = [test_icono_win, test_icono_loss, test_icono_empate,
             test_recuperacion_solo_con_flag,
             test_loss_sin_flag_no_lleva_recuperacion,
             test_win_no_lleva_recuperacion, test_precios_cinco_decimales,
             test_disclaimer_resultado]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
