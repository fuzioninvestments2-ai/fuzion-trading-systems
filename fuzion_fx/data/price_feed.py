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
