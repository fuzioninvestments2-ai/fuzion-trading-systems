"""
tests/test_po_history.py (fuzion_fx)
====================================
Valida el parser del historial de PO (collector/po_history.py) en sus dos formas:
velas OHLC (dict y lista) y linea de precios [t, precio] agregada por bucket. SIN
red: todo con payloads mock.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from collector.po_history import (normalizar_ts, parse_history)   # noqa: E402


def test_normalizar_ts_segundos_y_milisegundos() -> None:
    assert normalizar_ts(1_700_000_000) == 1_700_000_000
    # milisegundos (>1e12) -> se pasan a segundos.
    assert normalizar_ts(1_700_000_000_000) == 1_700_000_000
    assert normalizar_ts(None) is None
    assert normalizar_ts("x") is None


def test_parse_candles_dict() -> None:
    payload = {"asset": "EURUSD", "period": 60, "candles": [
        {"time": 120, "open": 1.10, "high": 1.12, "low": 1.09, "close": 1.11,
         "volume": 7},
        {"time": 60, "open": 1.09, "high": 1.10, "low": 1.08, "close": 1.10},
    ]}
    out = parse_history(payload)
    assert out["period"] == 60 and out["asset"] == "EURUSD"
    # Orden cronologico: primero ts=60, luego ts=120.
    assert [v[0] for v in out["velas"]] == [60, 120]
    assert out["velas"][1] == (120, 1.10, 1.12, 1.09, 1.11, 7.0)


def test_parse_candles_lista_orden_t_o_c_h_l() -> None:
    # Formato lista observado: [t, open, close, high, low, volume].
    payload = {"asset": "EURUSD", "period": 300,
               "data": [[300, 1.100, 1.105, 1.108, 1.099, 3]]}
    out = parse_history(payload)
    v = out["velas"][0]
    assert v == (300, 1.100, 1.108, 1.099, 1.105, 3.0)   # (ts,o,h,l,c,v)


def test_parse_linea_precios_agrega_por_bucket() -> None:
    # history [t, precio] a periodo 60: dos precios en el bucket 60, uno en el 120.
    payload = {"asset": "EURUSD", "period": 60, "history": [
        [60, 1.100], [90, 1.130], [120, 1.110]]}
    out = parse_history(payload)
    assert [v[0] for v in out["velas"]] == [60, 120]
    o, h, l, c = out["velas"][0][1:5]
    assert (o, h, l, c) == (1.100, 1.130, 1.100, 1.130)   # open=1.10 close=1.13(ultimo)


def test_parse_dedup_bucket_ultima_gana() -> None:
    # Dos velas al mismo bucket (60): la ultima pisa.
    payload = {"period": 60, "candles": [
        {"time": 60, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
        {"time": 95, "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0}]}
    out = parse_history(payload)
    assert len(out["velas"]) == 1 and out["velas"][0][4] == 2.0


def test_parse_vacio_o_invalido() -> None:
    assert parse_history(None) is None
    assert parse_history({"period": 60, "candles": []}) is None
    assert parse_history({"period": 60, "history": []}) is None


def _run_all() -> None:
    tests = [test_normalizar_ts_segundos_y_milisegundos, test_parse_candles_dict,
             test_parse_candles_lista_orden_t_o_c_h_l,
             test_parse_linea_precios_agrega_por_bucket,
             test_parse_dedup_bucket_ultima_gana, test_parse_vacio_o_invalido]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
