"""
bot/test_escaner_reversion.py
=============================
Valida sin red el escáner: filtra solo operables, ordena por probabilidad, arma la
tarjeta y el resumen.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.escaner_reversion import escanear, tarjeta, resumen


def test_escanear_filtra_y_ordena():
    velas = {
        "EURUSD": [1.1000, 1.1010],       # +10 pips -> prob más alta
        "GBPUSD": [1.2500, 1.2506],       # +6 pips
        "AUDUSD": [0.6500, 0.65012],      # 1.2 pips -> no opera
    }
    ops = escanear(velas)
    assert len(ops) == 2                                # AUDUSD queda fuera
    assert ops[0]["par"] == "EURUSD"                    # mayor probabilidad primero
    assert ops[0]["probabilidad"] >= ops[1]["probabilidad"]


def test_escanear_vacio_si_nada_opera():
    velas = {"EURUSD": [1.1000, 1.10010], "GBPUSD": [1.2500, 1.25008]}
    assert escanear(velas) == []


def test_tarjeta_operable_tiene_datos():
    ops = escanear({"USDJPY": [150.00, 149.94]})       # -6 pips -> CALL
    t = tarjeta(ops[0])
    assert "USDJPY" in t and "CALL" in t and "ARRIBA" in t
    assert "%" in t and "min" in t and "TIEMPO" in t


def test_tarjeta_sin_senal():
    from bot.senal_reversion import senal
    s = senal([1.1000, 1.10010], "EURUSD")             # pico chico
    t = tarjeta(s)
    assert "Sin señal" in t


def test_resumen():
    assert "sin reversiones" in resumen([]).lower()
    ops = escanear({"EURUSD": [1.1000, 1.1008]})
    assert "EURUSD" in resumen(ops)


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
