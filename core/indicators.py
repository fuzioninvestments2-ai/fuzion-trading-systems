"""Biblioteca de indicadores técnicos."""
from __future__ import annotations
import numpy as np
import pandas as pd


class Indicators:

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window).mean()

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(close: pd.Series, window: int = 20, std_dev: float = 2.0):
        sma = close.rolling(window).mean()
        std = close.rolling(window).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
        return upper, sma, lower, pct_b

    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                   k_period: int = 14, d_period: int = 3):
        low_min = low.rolling(k_period).min()
        high_max = high.rolling(k_period).max()
        k = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
        d = k.rolling(d_period).mean()
        return k, d

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        dm_plus = (high.diff()).clip(lower=0)
        dm_minus = (-low.diff()).clip(lower=0)
        di_plus = 100 * dm_plus.rolling(period).mean() / atr.replace(0, np.nan)
        di_minus = 100 * dm_minus.rolling(period).mean() / atr.replace(0, np.nan)
        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
        return dx.rolling(period).mean()

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        typical_price = (high + low + close) / 3
        return (typical_price * volume).cumsum() / volume.cumsum()

    @staticmethod
    def realized_volatility(close: pd.Series, window: int = 21) -> pd.Series:
        returns = close.pct_change()
        return returns.rolling(window).std() * np.sqrt(252)

    @staticmethod
    def squeeze_momentum(high: pd.Series, low: pd.Series, close: pd.Series,
                         bb_period: int = 20, kc_period: int = 20,
                         kc_mult: float = 1.5) -> pd.Series:
        """Bollinger Band dentro de Keltner Channel = squeeze."""
        bb_upper, bb_mid, bb_lower, _ = Indicators.bollinger_bands(close, bb_period)
        atr_val = Indicators.atr(high, low, close, kc_period)
        kc_upper = bb_mid + kc_mult * atr_val
        kc_lower = bb_mid - kc_mult * atr_val
        squeeze = (bb_upper < kc_upper) & (bb_lower > kc_lower)
        return squeeze.astype(float)
