"""
data/price_feed.py (fuzion_fx)
==============================
Fuente de velas OHLC por par y timeframe.

ESTADO: PLACEHOLDER. Todavia NO hay conexion a una API real de precios. Se define
la interfaz y un stub que devuelve None (sin datos) para que el bot corra SEGURO
sin emitir senales inventadas. Cuando se conecte el feed real (broker / API FX),
se implementa `get_candles` devolviendo velas reales.

HONESTIDAD (regla del proyecto): no se emulan ni inventan precios. Sin feed real,
el bot no emite.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

log = logging.getLogger("price_feed")


class PriceFeed:
    """Interfaz de feed de precios. Implementar `get_candles` con la API real."""

    def get_candles(self, pair: str, timeframe_seconds: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        """
        Debe devolver {'open','high','low','close'[,'volume']} con listas
        cronologicas (mas antigua -> reciente) de largo ~count, o None si no hay
        datos. Aca (placeholder) siempre None.
        """
        raise NotImplementedError


class StubPriceFeed(PriceFeed):
    """Feed vacio: devuelve None. Placeholder hasta conectar la API real."""

    def __init__(self) -> None:
        self._avisado = False

    def get_candles(self, pair: str, timeframe_seconds: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        if not self._avisado:
            log.warning("PriceFeed es un PLACEHOLDER: sin API real no hay velas, "
                        "el bot no emite senales. Implementa data/price_feed.py.")
            self._avisado = True
        return None


class InMemoryPriceFeed(PriceFeed):
    """
    Feed en memoria para pruebas/backtest: se le cargan velas por par y las
    devuelve. NO es red; sirve para testear el loop del bot sin internet.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, List[float]]] = {}

    def set_candles(self, pair: str, candles: Dict[str, Sequence[float]]) -> None:
        self._data[pair] = {k: list(v) for k, v in candles.items()}

    def get_candles(self, pair: str, timeframe_seconds: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        return self._data.get(pair)


class CandleStoreFeed(PriceFeed):
    """
    Feed REAL de los bots: lee las velas de po_candles.db que ESCRIBE el colector.
    Cada bot lee solo su par+timeframe (WHERE pair=? AND tf=?). Asi respetamos el
    limite de PO (una sola conexion, la del colector) con 4 procesos separados.

    Abre la sqlite en modo solo-lectura logico (no escribe). Si el archivo aun no
    existe (colector no arranco), get_candles devuelve None y el bot no emite.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._store = None            # perezoso: se abre cuando el archivo existe

    def _get_store(self):
        import os
        if self._store is not None:
            return self._store
        if self.db_path != ":memory:" and not os.path.exists(self.db_path):
            return None               # el colector todavia no creo la base
        from collector.candle_store import CandleStore
        self._store = CandleStore(self.db_path)
        return self._store

    def get_candles(self, pair: str, timeframe_seconds: int,
                    count: int = 200) -> Optional[Dict[str, List[float]]]:
        store = self._get_store()
        if store is None:
            return None
        return store.get_candles(pair, int(timeframe_seconds), count)

    def price_at(self, pair: str, timeframe_seconds: int,
                 ts: int) -> Optional[float]:
        """Cierre al vencimiento (para resolver senales). None si no hay dato."""
        store = self._get_store()
        if store is None:
            return None
        return store.price_at(pair, int(timeframe_seconds), int(ts))
