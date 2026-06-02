"""Dataclasses para datos de opciones."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd


@dataclass
class OptionContract:
    contract_symbol: str
    strike: float
    option_type: str        # "call" | "put"
    expiration: str
    dte: int
    last_price: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool
    mid_price: float = 0.0
    bid_ask_spread: float = 0.0
    moneyness: str = "OTM"  # ITM | ATM | OTM
    delta_estimate: float = 0.0
    low_liquidity: bool = False

    def __post_init__(self):
        if self.bid > 0 and self.ask > 0:
            self.mid_price = (self.bid + self.ask) / 2
        else:
            self.mid_price = self.last_price
        self.bid_ask_spread = self.ask - self.bid
        if self.mid_price > 0:
            self.low_liquidity = (self.bid_ask_spread / self.mid_price) > 0.20


@dataclass
class ChainData:
    symbol: str
    expiration: str
    dte: int
    underlying_price: float
    calls: List[OptionContract] = field(default_factory=list)
    puts: List[OptionContract] = field(default_factory=list)

    def calls_df(self) -> pd.DataFrame:
        return pd.DataFrame([vars(c) for c in self.calls])

    def puts_df(self) -> pd.DataFrame:
        return pd.DataFrame([vars(p) for p in self.puts])


@dataclass
class ExpirationInfo:
    expiration: str
    dte: int
    is_weekly: bool
    is_monthly: bool


@dataclass
class UnderlyingInfo:
    symbol: str
    price: float
    week_52_high: float
    week_52_low: float
    hv20: float
    hv50: float
    avg_volume: int
