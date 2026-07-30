"""
bot/test_confirmacion_reversion.py
==================================
Valida sin red la confirmación por extensión (z-score): confirma la reversión cuando
el precio está estirado en el sentido del pico y la rechaza cuando el pico es continuación
o no hay estiramiento. Sin muestra suficiente NO bloquea.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.confirmacion_reversion import z_score, confirma
from bot.senal_reversion import CALL, PUT


def test_z_score_estirado_arriba():
    closes = [1.0800] * 20 + [1.0815]           # salto claro sobre la media
    z = z_score(closes)
    assert z is not None and z > 3               # muy por encima de su media


def test_confirma_put_cuando_precio_estirado_arriba():
    closes = [1.0800] * 20 + [1.0815]
    assert confirma(closes, PUT) is True         # pico arriba y estirado -> PUT confirmado


def test_confirma_call_cuando_precio_estirado_abajo():
    closes = [1.0800] * 20 + [1.0785]
    assert confirma(closes, CALL) is True        # pico abajo y estirado -> CALL confirmado


def test_no_confirma_direccion_contraria():
    # Precio estirado ARRIBA pero la señal es CALL (incoherente) -> no confirma.
    closes = [1.0800] * 20 + [1.0815]
    assert confirma(closes, CALL) is False


def test_sin_muestra_no_bloquea():
    assert confirma([1.0800, 1.0810], PUT) is True   # pocas velas -> se confía en el borde


def test_desviacion_cero_no_bloquea():
    # Ventana plana (desviación 0): no se puede medir -> no bloquea.
    assert confirma([1.0800] * 21, PUT) is True


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
