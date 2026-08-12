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

from collector.po_collector import PocketOptionCollector, _po_code   # noqa: E402


def _colector(db_path: str) -> PocketOptionCollector:
    # ssid ficticio: el constructor de PocketOptionClient no abre conexion.
    return PocketOptionCollector('42["auth",{"session":"x"}]', db_path=db_path)


def test_po_code_otc_vs_real() -> None:
    # OTC (lo que opera el usuario): sufijo _otc en minuscula. Real: sin sufijo.
    assert _po_code("EUR/USD", "otc") == "EURUSD_otc"
    assert _po_code("GBP/JPY", "otc") == "GBPJPY_otc"
    assert _po_code("EUR/USD", "real") == "EURUSD"


def test_match_pair_robusto_por_formato() -> None:
    """El matcheo reconoce el par venga como venga y respeta el mercado."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        # Cualquier formato del MISMO mercado configurado mapea al par (CAD/JPY es
        # uno de los 22 pares del bot).
        if col.mercado == "real":
            assert col._match_pair("CADJPY") == "CAD/JPY"
            assert col._match_pair("cad/jpy") == "CAD/JPY"
            assert col._match_pair("CAD-JPY") == "CAD/JPY"
            # En real se IGNORA el simbolo OTC (otra serie de precio).
            assert col._match_pair("CADJPY_otc") is None
        else:
            assert col._match_pair("CADJPY_otc") == "CAD/JPY"
            assert col._match_pair("CADJPY") is None      # otc ignora el real
        # Par que no es nuestro -> None.
        assert col._match_pair("XAUUSD") is None
        assert col._match_pair("") is None
        assert col._match_pair(None) is None
        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_tick_mapea_al_par() -> None:
    """Un tick del activo que envia PO (segun el mercado configurado) mapea a
    'EUR/USD'. Se deriva el codigo del mercado real del colector para no depender
    de si el proyecto esta en real u otc."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        code = _po_code("EUR/USD", col.mercado)    # 'EURUSD' o 'EURUSD_otc'
        col._on_tick(code, 60, 1.2345)
        velas = col.store.get_candles("EUR/USD", 60)
        assert velas is not None and velas["close"][-1] == 1.2345
        col.store.close()
    finally:
        os.unlink(tmp.name)


def test_on_history_guarda_ohlc_real() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        col = _colector(tmp.name)
        # PO envia el activo del mercado configurado; el colector lo mapea al par
        # legible 'EUR/USD' en candles_real.
        code = _po_code("EUR/USD", col.mercado)
        payload = {"asset": code, "period": 300, "candles": [
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
        code = _po_code("EUR/USD", col.mercado)
        # period 7200 (2h) no esta en las temporalidades que junta el colector -> no
        # se guarda. (900=15m y 3600=1h SI se juntan ahora para la foto completa.)
        col._on_history({"asset": code, "period": 7200, "candles": [
            {"time": 7200, "open": 1, "high": 1, "low": 1, "close": 1}]})
        assert col.store.get_real_candles("EUR/USD", 7200) is None
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
    tests = [test_po_code_otc_vs_real,
             test_match_pair_robusto_por_formato,
             test_tick_mapea_al_par,
             test_on_history_guarda_ohlc_real,
             test_on_history_ignora_timeframe_no_usado,
             test_on_history_ignora_asset_desconocido]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
