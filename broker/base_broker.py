"""Interfaz abstracta para todos los brokers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AccountInfo:
    account_id: str
    equity: float
    cash: float
    buying_power: float
    paper_trading: bool
    currency: str = "USD"


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    side: str  # "long" | "short"


@dataclass
class Order:
    symbol: str
    qty: float
    side: str           # "buy" | "sell"
    order_type: str     # "market" | "limit" | "stop" | "stop_limit"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"
    client_order_id: str = ""


@dataclass
class OrderResult:
    order_id: str
    status: str
    symbol: str
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    error: str = ""


@dataclass
class MarketData:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    timestamp: str = ""


class BaseBroker(ABC):
    def __init__(self, config: dict):
        self._config = config
        self._paper_trading: bool = config.get("paper_trading", True)
        self._connected: bool = False

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def disconnect(self): ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo: ...

    @abstractmethod
    async def get_positions(self) -> List[Position]: ...

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketData: ...

    @abstractmethod
    async def get_options_chain(self, symbol: str, expiration: str) -> dict: ...

    def is_connected(self) -> bool:
        return self._connected

    def is_paper(self) -> bool:
        return self._paper_trading
