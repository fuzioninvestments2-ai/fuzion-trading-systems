"""
bot/test_tendencia.py
=====================
Valida sin red el filtro de tendencia: rechaza la reversión que pelea contra una
tendencia fuerte (el fallo real que se vio en las tarjetas) y la permite en rango.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.tendencia import fuerza_tendencia, permite_reversion
from bot.senal_reversion import CALL, PUT


def test_fuerza_positiva_en_subida():
    sube = [1.0800 + 0.0002 * i for i in range(20)] + [1.0850]
    assert fuerza_tendencia(sube) > 0.6                 # tendencia alcista clara


def test_rechaza_put_contra_subida():
    # El caso de la tarjeta: subida sostenida + pico arriba -> el bot decía PUT. Se veta.
    sube = [1.0800 + 0.0002 * i for i in range(20)] + [1.0850]
    assert permite_reversion(sube, PUT) is False


def test_rechaza_call_contra_bajada():
    baja = [1.0800 - 0.0002 * i for i in range(20)] + [1.0750]
    assert permite_reversion(baja, CALL) is False


def test_permite_put_en_rango():
    # En rango (sin tendencia) la reversión SÍ se permite: es donde tiene borde.
    rango = [1.0800, 1.0802, 1.0799, 1.0801, 1.0800] * 4 + [1.0810]
    assert permite_reversion(rango, PUT) is True


def test_permite_reversion_a_favor_de_la_tendencia():
    # Baja fuerte + pico ARRIBA (contra la tendencia) -> señal PUT va A FAVOR de la
    # bajada: se permite (es la reversión buena, el pop contra-tendencia que se devuelve).
    baja = [1.0800 - 0.0002 * i for i in range(20)] + [1.0810]
    assert permite_reversion(baja, PUT) is True


def test_sin_muestra_no_bloquea():
    assert permite_reversion([1.0800, 1.0810], PUT) is True


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
