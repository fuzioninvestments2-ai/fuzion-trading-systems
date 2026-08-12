"""
tests/test_comparar_historial.py (fuzion_fx)
============================================
Valida el nucleo puro de la herramienta de comparacion (Paso 1): metricas de
divergencia en pips sobre los timestamps comunes. SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.comparar_historial import (comparar_velas, _velas_close,   # noqa: E402
                                        _col_close)

_PIP = 0.0001                                   # par no-JPY


def test_sin_divergencia() -> None:
    po = [(60, 1.1000), (120, 1.1010)]
    col = [(60, 1.1000), (120, 1.1010)]
    r = comparar_velas(po, col, _PIP, umbral_pips=1.0)
    assert r["n_comunes"] == 2 and r["con_gap"] == 0
    assert r["gap_max_pips"] == 0.0 and r["pct_con_gap"] == 0.0


def test_divergencia_en_pips() -> None:
    # 1.1010 vs 1.1000 = 10 pips de gap en ts=120; ts=60 coincide.
    po = [(60, 1.1000), (120, 1.1010)]
    col = [(60, 1.1000), (120, 1.1000)]
    r = comparar_velas(po, col, _PIP, umbral_pips=1.0)
    assert r["n_comunes"] == 2
    assert r["gap_max_pips"] == 10.0
    assert r["con_gap"] == 1 and r["pct_con_gap"] == 50.0


def test_solo_cuenta_timestamps_comunes() -> None:
    # ts=180 solo esta en PO; ts=200 solo en colector: no cuentan como gap.
    po = [(60, 1.1000), (180, 1.2000)]
    col = [(60, 1.1000), (200, 1.9000)]
    r = comparar_velas(po, col, _PIP, umbral_pips=1.0)
    assert r["n_comunes"] == 1 and r["con_gap"] == 0
    assert r["solo_po"] == 1 and r["solo_col"] == 1


def test_adaptadores_desde_parse_y_store() -> None:
    parsed = {"period": 60, "velas": [(60, 1.1, 1.2, 1.0, 1.15, 3.0)]}
    assert _velas_close(parsed) == [(60, 1.15)]
    assert _velas_close(None) == []
    candles = {"ts": [60, 120], "close": [1.10, 1.11]}
    assert _col_close(candles) == [(60, 1.10), (120, 1.11)]
    assert _col_close(None) == []


def _run_all() -> None:
    tests = [test_sin_divergencia, test_divergencia_en_pips,
             test_solo_cuenta_timestamps_comunes, test_adaptadores_desde_parse_y_store]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
