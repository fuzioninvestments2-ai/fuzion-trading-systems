"""Pipeline de datos de mercado — yfinance por defecto."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf


class MarketData:
    def __init__(self, config: dict):
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_ts: Dict[str, float] = {}
        self._cache_ttl = config.get("cache_ttl_seconds", 300)

    def get_bars(self, symbol: str, period: str = "5y",
                 interval: str = "1d") -> pd.DataFrame:
        cache_key = f"{symbol}_{period}_{interval}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            raise ValueError(f"No se obtuvieron datos para {symbol}")

        df.columns = [c.lower() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df[["open", "high", "low", "close", "volume"]].dropna()

        self._cache[cache_key] = df
        self._cache_ts[cache_key] = time.time()
        return df

    def get_bars_range(self, symbol: str, start: str, end: str,
                       interval: str = "1d") -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            raise ValueError(f"No se obtuvieron datos para {symbol} ({start} → {end})")
        df.columns = [c.lower() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        return df[["open", "high", "low", "close", "volume"]].dropna()

    def get_latest_price(self, symbol: str) -> float:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            raise ValueError(f"No hay precio disponible para {symbol}")
        return float(hist["Close"].iloc[-1])

    def get_multiple(self, symbols: List[str], period: str = "5y") -> Dict[str, pd.DataFrame]:
        result = {}
        for sym in symbols:
            try:
                result[sym] = self.get_bars(sym, period=period)
            except Exception as e:
                print(f"[MarketData] Error obteniendo {sym}: {e}")
        return result

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return (time.time() - self._cache_ts.get(key, 0)) < self._cache_ttl
