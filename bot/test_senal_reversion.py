"""
bot/test_senal_reversion.py
===========================
Valida la máquina de señales de reversión (sin red): dirección contraria al pico,
piso y techo de pips, confianza por tramo, pip de JPY, y P&L esperado.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.senal_reversion import (senal, _pip, _prob_por_pico, _pnl_op, CALL, PUT,
                                 PISO_PIPS, MAX_PIPS, BREAKEVEN)


def test_pip_jpy():
    assert _pip("USDJPY") == 0.01
    assert _pip("EURUSD") == 0.0001


def test_subida_da_put():
    s = senal([1.1000, 1.1006], "EURUSD")              # subió 6 pips
    assert s["operar"] is True
    assert s["direccion"] == PUT                        # reversión: apuesta a que baja
    assert abs(s["pips"] - 6.0) < 0.01


def test_bajada_da_call():
    s = senal([1.1000, 1.09920], "EURUSD")             # bajó 8 pips
    assert s["operar"] is True
    assert s["direccion"] == CALL                       # reversión: apuesta a que sube


def test_pico_chico_no_opera():
    s = senal([1.1000, 1.10015], "EURUSD")             # 1.5 pips < piso
    assert s["operar"] is False
    assert "chico" in s["motivo"]


def test_pico_anomalo_no_opera():
    s = senal([1.1000, 1.1030], "EURUSD")              # 30 pips > MAX
    assert s["operar"] is False
    assert "anómalo" in s["motivo"]


def test_confianza_sube_con_el_pico():
    # A mayor pico, mayor win-rate histórico (borde monótono).
    p5 = _prob_por_pico(5)
    p10 = _prob_por_pico(10)
    assert p5 is not None and p10 is not None and p10 > p5
    assert _prob_por_pico(2) is None                   # bajo el piso -> sin tramo


def test_pnl_positivo_sobre_breakeven():
    # Todo tramo operable tiene win-rate > break-even -> P&L por operación positivo.
    for pips in (4, 5, 6, 8, 10):
        assert _prob_por_pico(pips) > BREAKEVEN
        assert _pnl_op(_prob_por_pico(pips)) > 0


def test_jpy_pips_correctos():
    s = senal([150.00, 150.05], "USDJPY")              # 5 pips en JPY (0.05)
    assert s["operar"] is True and abs(s["pips"] - 5.0) < 0.01
    assert s["direccion"] == PUT


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
