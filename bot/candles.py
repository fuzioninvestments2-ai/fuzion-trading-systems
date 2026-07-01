"""
bot/candles.py
==============
Constructor de VELAS (OHLC) a partir de TICKS.

EL PORQUÉ (corrección clave del blueprint):
En Pocket Option OTC en vivo solo llega el PRECIO suelto (tick), no velas ya
hechas. Pero los indicadores clásicos (MACD, Bollinger, patrones...) necesitan
velas con Open/High/Low/Close. Este módulo agrupa los ticks en "cubos" de tiempo
(ej. cada 60 s = vela M1) y forma cada vela:
  - Open  = primer precio del intervalo
  - High  = precio máximo del intervalo
  - Low   = precio mínimo del intervalo
  - Close = último precio del intervalo

Nota honesta sobre el VOLUMEN: OTC normalmente no da volumen real, así que aquí
`volume` es el NÚMERO DE TICKS de la vela (un sustituto, NO volumen real). Se
documenta para no engañar a los indicadores de volumen.

SRP: este módulo solo agrega ticks en velas. No sabe de estrategia ni de red.
"""

from collections import deque

import pandas as pd


class CandleBuilder:
    """
    Agrega ticks en velas de tamaño fijo (`timeframe_seconds`).

    Uso:
        cb = CandleBuilder(60)                 # velas de 1 minuto
        vela = cb.add_tick(precio, ts_ms)      # devuelve una vela CERRADA o None
        df = cb.to_dataframe()                 # velas cerradas como DataFrame
    """

    def __init__(self, timeframe_seconds, max_candles=500):
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds debe ser > 0")
        self.tf_ms = timeframe_seconds * 1000.0
        # Buffer de velas CERRADAS (tamaño acotado -> memoria constante 24/7).
        self._candles = deque(maxlen=max_candles)
        self._current = None        # vela en formación
        self._bucket = None         # inicio (ms) del intervalo actual

    def _bucket_start(self, ts_ms):
        """Inicio del 'cubo' de tiempo al que pertenece este timestamp."""
        return (ts_ms // self.tf_ms) * self.tf_ms

    def add_tick(self, price, ts_ms):
        """
        Procesa un tick. Si el tick pertenece a un intervalo NUEVO, cierra la
        vela anterior (la devuelve) y empieza una nueva. Si no, actualiza la
        vela en formación y devuelve None.
        """
        price = float(price)
        bucket = self._bucket_start(float(ts_ms))
        closed = None

        if self._current is None:
            # Primera vela.
            self._bucket = bucket
            self._current = self._new_candle(bucket, price)
        elif bucket != self._bucket:
            # Cambió el intervalo -> se cierra la vela actual y arranca otra.
            closed = self._current
            self._candles.append(closed)
            self._bucket = bucket
            self._current = self._new_candle(bucket, price)
        else:
            # Mismo intervalo -> actualizar High/Low/Close y contar el tick.
            c = self._current
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
            c["volume"] += 1

        return closed

    @staticmethod
    def _new_candle(bucket_start_ms, price):
        # Al abrir, O=H=L=C=primer precio; 1 tick contado.
        return {
            "timestamp": bucket_start_ms,
            "open": price, "high": price, "low": price, "close": price,
            "volume": 1,
        }

    def closed_candles(self):
        """Lista de velas ya cerradas (sin la que está en formación)."""
        return list(self._candles)

    def to_dataframe(self, include_forming=False):
        """
        Devuelve las velas como DataFrame (columns: timestamp, open, high, low,
        close, volume). Si include_forming=True, añade la vela en formación al
        final (útil para analizar "en vivo" el último precio).
        """
        rows = list(self._candles)
        if include_forming and self._current is not None:
            rows = rows + [self._current]
        if not rows:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(rows)
