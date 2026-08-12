"""
tests/test_collector_history.py (fuzion_fx)
===========================================
Valida que el colector guarde el OHLC REAL de PO en candles_real al recibir
on_history (Paso 2): mapea asset->par, filtra timeframes no usados y persiste. SIN
red: se construye el colector con un ssid ficticio y se le inyecta el payload a
mano (el cliente no conecta en el constructor).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
_REPO_ROOT = os.path.dirname(_RAIZ)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

from collector.po_collector import PocketOptionCollector      # noqa: E402


def _colector(db_path: str) -> PocketOptionCollector:
    # ssid ficticio: el constructor de PocketOptionClient no abre conexion.
    return PocketOptionCollector('42["auth",{"session":"x"}]', db_path=db_path)


def test_on_history_guarda_ohlc_real() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        payload = {"asset": "EURUSD", "period": 300, "candles": [
            {"time": 300, "open": 1.10, "high": 1.12, "low": 1.09, "close": 1.11,
             "volume": 4},
            {"time": 600, "open": 1.11, "high": 1.13, "low": 1.10, "close": 1.125,
             "volume": 6}]}
        col._on_history(payload)
        real = col.store.get_real_candles("EUR/USD", 300)
        assert real["close"] == [1.11, 1.125]
        # No se toco la tabla de ticks.
        assert col.store.get_candles("EUR/USD", 300) is None
        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_on_history_ignora_timeframe_no_usado() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        # period 900 no lo analiza ningun bot -> no se guarda.
        col._on_history({"asset": "EURUSD", "period": 900, "candles": [
            {"time": 900, "open": 1, "high": 1, "low": 1, "close": 1}]})
        assert col.store.get_real_candles("EUR/USD", 900) is None
        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_on_history_ignora_asset_desconocido() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        # Asset que no esta entre los 22 pares -> se ignora sin romper.
        col._on_history({"asset": "XAUUSD", "period": 60, "candles": [
            {"time": 60, "open": 1, "high": 1, "low": 1, "close": 1}]})
        assert col.store.get_real_candles("XAU/USD", 60) is None
        col.store.close()
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_on_history_guarda_ohlc_real,
             test_on_history_ignora_timeframe_no_usado,
             test_on_history_ignora_asset_desconocido]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
