"""
tests/test_analisis_visual.py (fuzion_fx)
=========================================
Valida el panel visual: calculo de win-rate por grupo y que genera el PNG (con datos
y vacio). SIN red.
"""
from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import analisis_visual as av                       # noqa: E402


def _filas():
    # 3 setups; A gana, B pierde, con horas/pares/tf variados.
    out = []
    for i in range(6):
        out.append({"tf": "5m", "pair": "EUR/USD", "setup": "A",
                    "result": "win" if i % 3 else "loss", "ts": 1000 + i, "hora": 9})
    for i in range(6):
        out.append({"tf": "1m", "pair": "GBP/JPY", "setup": "B",
                    "result": "loss", "ts": 2000 + i, "hora": 2})
    return out


def test_wr_cuenta_bien() -> None:
    wr, n = av._wr(_filas()[:6])          # setup A: 4 win / 2 loss
    assert n == 6 and abs(wr - 66.6667) < 0.01


def test_genera_png_con_datos() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        out = av.graficar(_filas(), tmp.name, min_n=3)
        assert os.path.exists(out) and os.path.getsize(out) > 1000
    finally:
        os.unlink(tmp.name)


def test_genera_png_vacio_no_revienta() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        out = av.graficar([], tmp.name)
        assert os.path.exists(out) and os.path.getsize(out) > 500
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    for fn in (test_wr_cuenta_bien, test_genera_png_con_datos,
               test_genera_png_vacio_no_revienta):
        fn()
        print(f"  OK  {fn.__name__}")
    print("3 tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
