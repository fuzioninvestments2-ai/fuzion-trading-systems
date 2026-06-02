"""
Options Chain Fetcher — yfinance / Polygon.
Expiración mensual más cercana (tercer viernes del mes, NO weekly).
"""
from __future__ import annotations
import json
import math
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from .chain_models import ChainData, ExpirationInfo, OptionContract, UnderlyingInfo
from .greeks_calculator import GreeksCalculator


class OptionsChainFetcher:
    def __init__(self, cache_dir: str = "./cache", cache_ttl_minutes: int = 15,
                 data_source: str = "yfinance"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(exist_ok=True)
        self._ttl = cache_ttl_minutes * 60
        self._source = data_source
        self._greeks = GreeksCalculator()
        self._rf_rate = 0.05

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def get_chain(self, symbol: str, expiration: Optional[str] = None) -> ChainData:
        all_exps = self.get_all_expirations(symbol)
        if not all_exps:
            raise ValueError(f"No hay expiraciones disponibles para {symbol}")

        if expiration is None:
            monthly = [e for e in all_exps if e.is_monthly and 15 <= e.dte <= 60]
            if not monthly:
                monthly = [e for e in all_exps if 15 <= e.dte <= 60]
            expiration = monthly[0].expiration if monthly else all_exps[0].expiration

        cache_key = f"{symbol}_{expiration}"
        cached = self._load_cache(cache_key)
        if cached:
            return cached

        chain = self._fetch_chain_yfinance(symbol, expiration)
        self._save_cache(cache_key, chain)
        return chain

    def get_all_expirations(self, symbol: str) -> List[ExpirationInfo]:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        today = date.today()
        result = []
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte < 0:
                continue
            is_monthly = self._is_monthly_expiry(exp_date)
            result.append(ExpirationInfo(
                expiration=exp_str, dte=dte,
                is_weekly=not is_monthly, is_monthly=is_monthly,
            ))
        return sorted(result, key=lambda e: e.dte)

    def get_multi_expiry_chain(self, symbol: str,
                                dte_range: Tuple[int, int] = (7, 90)) -> Dict[str, ChainData]:
        all_exps = self.get_all_expirations(symbol)
        result = {}
        for exp in all_exps:
            if dte_range[0] <= exp.dte <= dte_range[1]:
                try:
                    result[exp.expiration] = self.get_chain(symbol, exp.expiration)
                except Exception:
                    pass
        return result

    def get_underlying_price(self, symbol: str) -> UnderlyingInfo:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="1y")
        close = hist["Close"]
        hv20 = float(close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252))
        hv50 = float(close.pct_change().rolling(50).std().iloc[-1] * np.sqrt(252))
        return UnderlyingInfo(
            symbol=symbol,
            price=float(info.get("regularMarketPrice", close.iloc[-1])),
            week_52_high=float(info.get("fiftyTwoWeekHigh", close.max())),
            week_52_low=float(info.get("fiftyTwoWeekLow", close.min())),
            hv20=round(hv20, 4),
            hv50=round(hv50, 4),
            avg_volume=int(info.get("averageVolume", 0)),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_chain_yfinance(self, symbol: str, expiration: str) -> ChainData:
        ticker = yf.Ticker(symbol)
        underlying = self.get_underlying_price(symbol)
        S = underlying.price

        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        dte = (exp_date - date.today()).days
        T = max(dte / 365, 1 / 365)

        chain = ticker.option_chain(expiration)
        calls = self._parse_contracts(chain.calls, "call", S, T)
        puts = self._parse_contracts(chain.puts, "put", S, T)

        return ChainData(symbol=symbol, expiration=expiration,
                         dte=dte, underlying_price=S, calls=calls, puts=puts)

    def _parse_contracts(self, df: pd.DataFrame, option_type: str,
                          S: float, T: float) -> List[OptionContract]:
        contracts = []
        for _, row in df.iterrows():
            strike = float(row["strike"])
            bid = float(row.get("bid", 0) or 0)
            ask = float(row.get("ask", 0) or 0)
            last = float(row.get("lastPrice", 0) or 0)
            iv = float(row.get("impliedVolatility", 0) or 0)
            volume = int(row.get("volume", 0) or 0)
            oi = int(row.get("openInterest", 0) or 0)
            itm = bool(row.get("inTheMoney", False))

            # Moneyness
            moneyness_pct = abs(S - strike) / S
            if moneyness_pct <= 0.005:
                moneyness = "ATM"
            elif (option_type == "call" and S > strike) or (option_type == "put" and S < strike):
                moneyness = "ITM"
            else:
                moneyness = "OTM"

            # Delta estimado
            delta_est = 0.0
            if iv > 0:
                try:
                    g = self._greeks.calculate_all_greeks(S, strike, T, self._rf_rate, iv, option_type)
                    delta_est = g.delta
                except Exception:
                    pass

            contracts.append(OptionContract(
                contract_symbol=str(row.get("contractSymbol", "")),
                strike=strike, option_type=option_type,
                expiration="", dte=int(T * 365),
                last_price=last, bid=bid, ask=ask,
                volume=volume, open_interest=oi,
                implied_volatility=iv, in_the_money=itm,
                moneyness=moneyness, delta_estimate=delta_est,
            ))
        return contracts

    @staticmethod
    def _is_monthly_expiry(exp_date: date) -> bool:
        """Tercer viernes del mes."""
        if exp_date.weekday() != 4:  # 4 = viernes
            return False
        first_day = exp_date.replace(day=1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(weeks=2)
        return exp_date == third_friday

    def _load_cache(self, key: str) -> Optional[ChainData]:
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._ttl:
            return None
        try:
            data = json.loads(path.read_text())
            return self._deserialize_chain(data)
        except Exception:
            return None

    def _save_cache(self, key: str, chain: ChainData) -> None:
        path = self._cache_dir / f"{key}.json"
        try:
            path.write_text(json.dumps(self._serialize_chain(chain)))
        except Exception:
            pass

    @staticmethod
    def _serialize_chain(chain: ChainData) -> dict:
        def contract_to_dict(c: OptionContract) -> dict:
            return vars(c)
        return {
            "symbol": chain.symbol, "expiration": chain.expiration,
            "dte": chain.dte, "underlying_price": chain.underlying_price,
            "calls": [contract_to_dict(c) for c in chain.calls],
            "puts": [contract_to_dict(p) for p in chain.puts],
        }

    @staticmethod
    def _deserialize_chain(data: dict) -> ChainData:
        calls = [OptionContract(**c) for c in data["calls"]]
        puts = [OptionContract(**p) for p in data["puts"]]
        return ChainData(
            symbol=data["symbol"], expiration=data["expiration"],
            dte=data["dte"], underlying_price=data["underlying_price"],
            calls=calls, puts=puts,
        )
