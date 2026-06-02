"""IV Analyzer — Rank, Percentile, Term Structure, Skew."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
import yfinance as yf
from .chain_fetcher import OptionsChainFetcher
from .chain_models import ChainData


@dataclass
class SkewData:
    put_skew: float
    call_skew: float
    skew_ratio: float


@dataclass
class IVHVComparison:
    current_iv: float
    hv20: float
    hv50: float
    iv_premium: float


class IVAnalyzer:
    def __init__(self, fetcher: Optional[OptionsChainFetcher] = None):
        self._fetcher = fetcher or OptionsChainFetcher()

    def iv_rank(self, symbol: str, lookback_days: int = 252) -> float:
        iv_series = self._get_iv_history(symbol, lookback_days)
        if iv_series.empty:
            return 50.0
        current = iv_series.iloc[-1]
        iv_min = iv_series.min()
        iv_max = iv_series.max()
        if iv_max == iv_min:
            return 50.0
        return round(100 * (current - iv_min) / (iv_max - iv_min), 2)

    def iv_percentile(self, symbol: str, lookback_days: int = 252) -> float:
        iv_series = self._get_iv_history(symbol, lookback_days)
        if iv_series.empty:
            return 50.0
        current = iv_series.iloc[-1]
        return round(100 * (iv_series < current).mean(), 2)

    def iv_term_structure(self, symbol: str) -> pd.DataFrame:
        chains = self._fetcher.get_multi_expiry_chain(symbol, dte_range=(7, 180))
        rows = []
        for exp, chain in chains.items():
            atm_iv = self._atm_iv(chain)
            rows.append({"expiration": exp, "dte": chain.dte, "iv": atm_iv})
        return pd.DataFrame(rows).sort_values("dte")

    def iv_skew(self, chain: ChainData) -> SkewData:
        S = chain.underlying_price
        puts_otm = [p for p in chain.puts if p.moneyness == "OTM" and p.implied_volatility > 0]
        calls_otm = [c for c in chain.calls if c.moneyness == "OTM" and c.implied_volatility > 0]
        atm_iv = self._atm_iv(chain)
        put_skew = (np.mean([p.implied_volatility for p in puts_otm]) - atm_iv) if puts_otm else 0.0
        call_skew = (np.mean([c.implied_volatility for c in calls_otm]) - atm_iv) if calls_otm else 0.0
        skew_ratio = (put_skew / call_skew) if call_skew != 0 else 0.0
        return SkewData(put_skew=round(put_skew, 4), call_skew=round(call_skew, 4),
                        skew_ratio=round(skew_ratio, 4))

    def iv_vs_hv(self, symbol: str) -> IVHVComparison:
        underlying = self._fetcher.get_underlying_price(symbol)
        try:
            chain = self._fetcher.get_chain(symbol)
            current_iv = self._atm_iv(chain)
        except Exception:
            current_iv = underlying.hv20
        return IVHVComparison(
            current_iv=round(current_iv, 4),
            hv20=round(underlying.hv20, 4),
            hv50=round(underlying.hv50, 4),
            iv_premium=round(current_iv - underlying.hv20, 4),
        )

    @staticmethod
    def _atm_iv(chain: ChainData) -> float:
        atm_contracts = [c for c in chain.calls + chain.puts
                         if c.moneyness == "ATM" and c.implied_volatility > 0]
        if not atm_contracts:
            all_iv = [c.implied_volatility for c in chain.calls + chain.puts
                      if c.implied_volatility > 0]
            return float(np.median(all_iv)) if all_iv else 0.0
        return float(np.mean([c.implied_volatility for c in atm_contracts]))

    def _get_iv_history(self, symbol: str, lookback_days: int) -> pd.Series:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{lookback_days + 30}d")
        if hist.empty:
            return pd.Series()
        close = hist["Close"]
        hv = close.pct_change().rolling(20).std() * np.sqrt(252)
        return hv.dropna().tail(lookback_days)
