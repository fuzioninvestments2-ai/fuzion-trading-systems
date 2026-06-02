"""Interactive Brokers adapter — ib_insync SDK."""
from __future__ import annotations
import os
from typing import List
from ib_insync import IB, Stock, MarketOrder, LimitOrder, StopOrder, util
from .base_broker import BaseBroker, AccountInfo, Position, Order, OrderResult, MarketData


class IBKRClient(BaseBroker):
    """
    Conexión via TWS/Gateway socket.
    Paper: port 7497 | Live: port 7496
    """
    def __init__(self, config: dict):
        super().__init__(config)
        self._host = config.get("host", "127.0.0.1")
        paper = config.get("paper_trading", True)
        self._port = 7497 if paper else 7496
        self._client_id = config.get("client_id", 1)
        self._ib = IB()

    async def connect(self) -> bool:
        try:
            await self._ib.connectAsync(self._host, self._port, clientId=self._client_id)
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"IBKR connect error: {e}")

    async def disconnect(self):
        if self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        summary = await self._ib.accountSummaryAsync()
        values = {s.tag: float(s.value) for s in summary if s.currency == "USD"}
        return AccountInfo(
            account_id=self._ib.client.accounts()[0] if self._ib.client.accounts() else "",
            equity=values.get("NetLiquidation", 0.0),
            cash=values.get("CashBalance", 0.0),
            buying_power=values.get("BuyingPower", 0.0),
            paper_trading=self._paper_trading,
        )

    async def get_positions(self) -> List[Position]:
        positions = await self._ib.reqPositionsAsync()
        result = []
        for p in positions:
            result.append(Position(
                symbol=p.contract.symbol,
                qty=float(p.position),
                avg_price=float(p.avgCost),
                current_price=0.0,
                unrealized_pnl=0.0,
                side="long" if p.position > 0 else "short",
            ))
        return result

    async def place_order(self, order: Order) -> OrderResult:
        contract = Stock(order.symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)

        if order.order_type == "market":
            ib_order = MarketOrder(order.side.upper(), order.qty)
        elif order.order_type == "limit":
            ib_order = LimitOrder(order.side.upper(), order.qty, order.limit_price)
        elif order.order_type == "stop":
            ib_order = StopOrder(order.side.upper(), order.qty, order.stop_price)
        else:
            ib_order = MarketOrder(order.side.upper(), order.qty)

        # Stop-only-tightens
        ib_order.tif = order.time_in_force.upper()

        trade = self._ib.placeOrder(contract, ib_order)
        return OrderResult(
            order_id=str(trade.order.orderId),
            status=trade.orderStatus.status,
            symbol=order.symbol,
        )

    async def cancel_order(self, order_id: str) -> bool:
        try:
            orders = self._ib.orders()
            for o in orders:
                if str(o.orderId) == order_id:
                    self._ib.cancelOrder(o)
                    return True
            return False
        except Exception:
            return False

    async def get_market_data(self, symbol: str) -> MarketData:
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        ticker = self._ib.reqMktData(contract, "", False, False)
        await self._ib.sleep(1)
        return MarketData(
            symbol=symbol,
            bid=float(ticker.bid or 0),
            ask=float(ticker.ask or 0),
            last=float(ticker.last or 0),
            volume=int(ticker.volume or 0),
        )

    async def get_options_chain(self, symbol: str, expiration: str) -> dict:
        from ib_insync import Option
        chains = await self._ib.reqSecDefOptParamsAsync(symbol, "", "STK", 0)
        return {"chains": [str(c) for c in chains], "expiration": expiration}
