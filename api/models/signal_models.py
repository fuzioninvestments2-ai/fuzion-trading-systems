from pydantic import BaseModel
from typing import List, Optional


class SignalRequest(BaseModel):
    symbols: Optional[List[str]] = None
    symbol: Optional[str] = None       # alias para un solo símbolo
    period: str = "2y"
    equity: Optional[float] = None     # ignorado, para compatibilidad frontend

    def get_symbols(self) -> List[str]:
        if self.symbols:
            return self.symbols
        if self.symbol:
            return [self.symbol]
        return []


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
