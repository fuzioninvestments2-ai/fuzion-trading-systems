"""Feature engineering — 14 features z-scored para HMM."""
from __future__ import annotations
import numpy as np
import pandas as pd
from core.indicators import Indicators


class FeatureEngineer:
    def __init__(self, zscore_window: int = 126):
        self.zscore_window = zscore_window

    def build_features(self, bars: pd.DataFrame) -> pd.DataFrame:
        df = bars.copy()
        close = df["close"]
        high = df.get("high", close)
        low = df.get("low", close)
        volume = df.get("volume", pd.Series(np.ones(len(df)), index=df.index))

        features = pd.DataFrame(index=df.index)
        features["ret_1d"] = close.pct_change(1)
        features["ret_5d"] = close.pct_change(5)
        features["ret_21d"] = close.pct_change(21)
        features["vol_10d"] = features["ret_1d"].rolling(10).std() * np.sqrt(252)
        features["vol_21d"] = features["ret_1d"].rolling(21).std() * np.sqrt(252)
        features["vol_ratio_change"] = features["vol_10d"] / features["vol_21d"].replace(0, np.nan)
        vol_ma = volume.rolling(21).mean()
        features["volume_ratio"] = volume / vol_ma.replace(0, np.nan)
        ema20 = Indicators.ema(close, 20)
        ema50 = Indicators.ema(close, 50)
        features["trend_ema20"] = (close - ema20) / ema20
        features["trend_ema50"] = (close - ema50) / ema50
        features["rsi14"] = Indicators.rsi(close, 14)
        _, signal_line, _ = Indicators.macd(close)
        features["macd_signal"] = signal_line
        _, _, _, pct_b = Indicators.bollinger_bands(close, 20)
        features["bollinger_pct_b"] = pct_b
        k, _ = Indicators.stochastic(high, low, close, 14)
        features["stoch_k"] = k
        features["adx"] = Indicators.adx(high, low, close, 14)

        return self._rolling_zscore(features)

    def _rolling_zscore(self, features: pd.DataFrame) -> pd.DataFrame:
        zscored = pd.DataFrame(index=features.index, columns=features.columns, dtype=float)
        for col in features.columns:
            s = features[col]
            roll_mean = s.rolling(self.zscore_window, min_periods=30).mean()
            roll_std = s.rolling(self.zscore_window, min_periods=30).std()
            zscored[col] = (s - roll_mean) / roll_std.replace(0, np.nan)
        return zscored.clip(-5, 5)
