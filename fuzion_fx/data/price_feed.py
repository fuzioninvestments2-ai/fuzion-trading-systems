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
        # Pago por par para el filtro; default 85 (en rango) para que las pruebas
        # de emision no queden mudas por el filtro de pago.
        self._payouts: Dict[str, float] = {}
        self._payout_default: Optional[float] = 85.0

    def set_candles(self, pair: str, candles: Dict[str, Sequence[float]]) -> None:
        self._data[pair] = {k: list(v) for k, v in candles.items()}

    def set_payout(self, pair: str, payout: Optional[float]) -> None:
        """Fija el pago (%) de un par para probar el filtro de pago."""
        self._payouts[pair] = payout

    def get_payout(self, pair: str) -> Optional[float]:
        return self._payouts.get(pair, self._payout_default)

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
        """
        Velas para el analisis. PRIORIZA el OHLC real de PO (candles_real, fuente
        de verdad); solo cae a los ticks ralos (candles) como backup cuando aun no
        hay velas reales de ese par+tf. Asi las senales se calculan sobre el precio
        real, no sobre el tick viciado.
        """
        store = self._get_store()
        if store is None:
            return None
        tf = int(timeframe_seconds)
        real = store.get_real_candles(pair, tf, count)
        if real and len(real.get("close", [])) >= 2:
            return real
        return store.get_candles(pair, tf, count)

    def price_at(self, pair: str, timeframe_seconds: int,
                 ts: int) -> Optional[float]:
        """Cierre al vencimiento sobre TICKS (backup/legado). Ver price_at_real."""
        store = self._get_store()
        if store is None:
            return None
        return store.price_at(pair, int(timeframe_seconds), int(ts))

    def price_at_real(self, pair: str, timeframe_seconds: int,
                      ts: int) -> Optional[float]:
        """Cierre REAL de PO en la vela que contiene `ts`. None si no hay dato real."""
        store = self._get_store()
        if store is None:
            return None
        return store.price_at_real(pair, int(timeframe_seconds), int(ts))

    def real_candle_at(self, pair: str, timeframe_seconds: int, bucket: int):
        """(open, close) REAL de la vela en el bucket exacto. None si no hay dato."""
        store = self._get_store()
        if store is None:
            return None
        return store.real_candle_at(pair, int(timeframe_seconds), int(bucket))

    def get_payout(self, pair: str) -> Optional[float]:
        """Pago real (%) del par que guardo el colector. None si aun no llego."""
        store = self._get_store()
        if store is None:
            return None
        return store.get_payout(pair)
