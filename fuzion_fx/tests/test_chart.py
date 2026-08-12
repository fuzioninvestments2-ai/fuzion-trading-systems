"""
tests/test_chart.py (fuzion_fx)
===============================
Valida el grafico de velas coordinado con la senal (render_candles): produce PNG,
usa la direccion y el precio de entrada sin romper, y devuelve None con pocos
datos. SIN red (matplotlib backend Agg).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from telegram.chart import render_candles                        # noqa: E402


def _velas(n=40):
    o = [1.1000 + i * 0.0001 for i in range(n)]
    h = [x + 0.0002 for x in o]
    l = [x - 0.0002 for x in o]
    c = [x + 0.0001 for x in o]
    return {"open": o, "high": h, "low": l, "close": c}


def _png_bytes(buf):
    assert buf is not None
    data = buf.getvalue()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"      # firma PNG valida
    assert len(data) > 500
    return data


def test_render_call_y_put_producen_png() -> None:
    _png_bytes(render_candles(_velas(), "EUR/USD M1", "CALL", entry_price=1.1030))
    _png_bytes(render_candles(_velas(), "EUR/USD M1", "PUT", entry_price=1.1030))


def test_render_sin_direccion_tambien_dibuja() -> None:
    _png_bytes(render_candles(_velas(), "EUR/USD M1", ""))


def test_render_pocos_datos_devuelve_none() -> None:
    assert render_candles({"open": [1], "high": [1], "low": [1], "close": [1]},
                          "x", "CALL") is None


def test_render_sin_entry_usa_ultimo_cierre() -> None:
    # No debe romper si no se pasa entry_price (cae al ultimo cierre).
    _png_bytes(render_candles(_velas(), "EUR/USD M1", "PUT"))


def _run_all() -> None:
    tests = [test_render_call_y_put_producen_png,
             test_render_sin_direccion_tambien_dibuja,
             test_render_pocos_datos_devuelve_none,
             test_render_sin_entry_usa_ultimo_cierre]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
