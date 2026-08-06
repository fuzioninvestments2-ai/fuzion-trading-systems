"""
collector/aggregator.py (fuzion_fx)
===================================
Agrega TICKS (precio suelto) en VELAS OHLC por timeframe.

Pocket Option manda ticks (asset, ts, precio). Este agregador arma, para cada
par y cada timeframe (60/120/180/300s), la vela en curso y avisa cuando una vela
CIERRA (para persistirla definitiva). El inicio de vela se alinea a multiplos del
timeframe: bucket = ts - (ts % tf).

SRP: solo agrega ticks en velas. No sabe de red ni de sqlite. Se prueba sin red.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

# (open, high, low, close) de la vela en formacion.
_OHLC = Dict[str, float]


class CandleAggregator:
    def __init__(self, timeframes: List[int]) -> None:
        self.timeframes = list(timeframes)
        # estado[(pair, tf)] = {"bucket": ts_inicio, "o","h","l","c","v"}
        self._estado: Dict[Tuple[str, int], Dict[str, float]] = {}

    def add_tick(self, pair: str, ts: int, price: float
                 ) -> List[Tuple[str, int, int, _OHLC]]:
        """
        Procesa un tick. Devuelve la lista de velas CERRADAS por este tick, como
        (pair, tf, bucket_ts, {open,high,low,close,volume}). La vela EN CURSO no
        se devuelve aca (se consulta con `current`); el colector la puede upsertear
        igual para tener el precio vivo.
        """
        ts = int(ts)
        price = float(price)
        cerradas = []
        for tf in self.timeframes:
            bucket = ts - (ts % tf)
            key = (pair, tf)
            v = self._estado.get(key)
            if v is None:
                # Primera vela de este par+tf.
                self._estado[key] = {"bucket": bucket, "o": price, "h": price,
                                     "l": price, "c": price, "v": 1}
                continue
            if bucket > v["bucket"]:
                # Cambio de vela: la anterior CIERRA y arranca una nueva.
                cerradas.append((pair, tf, int(v["bucket"]),
                                 {"open": v["o"], "high": v["h"], "low": v["l"],
                                  "close": v["c"], "volume": v["v"]}))
                self._estado[key] = {"bucket": bucket, "o": price, "h": price,
                                     "l": price, "c": price, "v": 1}
            else:
                # Mismo bucket: actualiza high/low/close y cuenta el tick.
                v["h"] = max(v["h"], price)
                v["l"] = min(v["l"], price)
                v["c"] = price
                v["v"] += 1
        return cerradas

    def current(self, pair: str, tf: int) -> Optional[Tuple[int, _OHLC]]:
        """Vela EN FORMACION del par+tf: (bucket_ts, {ohlcv}) o None."""
        v = self._estado.get((pair, tf))
        if v is None:
            return None
        return int(v["bucket"]), {"open": v["o"], "high": v["h"], "low": v["l"],
                                  "close": v["c"], "volume": v["v"]}
