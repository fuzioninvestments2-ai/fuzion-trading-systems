from pydantic import BaseModel
from typing import List, Optional


class SignalRequest(BaseModel):
    symbols: List[str]
    period: str = "2y"


class BrokerConnectRequest(BaseModel):
    broker: str = "alpaca"
    paper_trading: bool = True


class TradeExecutionRequest(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    position_size_pct: float = 0.05
    leverage: float = 1.0
    take_profit: Optional[float] = None
    strategy_name: str = ""
