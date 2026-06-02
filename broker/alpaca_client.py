"""Alpaca broker adapter — REST API gratuita."""
from __future__ import annotations
import os
from typing import List
import alpaca_trade_api as tradeapi
from .base_broker import BaseBroker, AccountInfo, Position, Order, OrderResult, MarketData


class AlpacaClient(BaseBroker):
    def __init__(self, config: dict):
        super().__init__(config)
        self._api_key = config.get("api_key") or os.getenv("ALPACA_API_KEY", "")
        self._secret = config.get("secret_key") or os.getenv("ALPACA_SECRET_KEY", "")
        paper = config.get("paper_trading", True)
        self._base_url = ("https://paper-api.alpaca.markets" if paper
                          else "https://api.alpaca.markets")
        self._api: tradeapi.REST = None

    async def connect(self) -> bool:
        try:
            self._api = tradeapi.REST(self._api_key, self._secret, self._base_url)
            self._api.get_account()
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Alpaca connect error: {e}")

    async def disconnect(self):
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        acc = self._api.get_account()
        return AccountInfo(
            account_id=acc.id,
            equity=float(acc.equity),
            cash=float(acc.cash),
            buying_power=float(acc.buying_power),
            paper_trading=self._paper_trading,
        )

    async def get_positions(self) -> List[Position]:
        positions = self._api.list_positions()
        return [
            Position(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pnl=float(p.unrealized_pl),
                side="long" if float(p.qty) > 0 else "short",
            )
            for p in positions
        ]

    async def place_order(self, order: Order) -> OrderResult:
        try:
            kwargs = dict(
                symbol=order.symbol,
                qty=order.qty,
                side=order.side,
                type=order.order_type,
                time_in_force=order.time_in_force,
            )
            if order.limit_price:
                kwargs["limit_price"] = order.limit_price
            if order.stop_price:
                kwargs["stop_price"] = order.stop_price
            if order.client_order_id:
                kwargs["client_order_id"] = order.client_order_id

            o = self._api.submit_order(**kwargs)
            return OrderResult(
                order_id=o.id,
                status=o.status,
                symbol=o.symbol,
                filled_qty=float(o.filled_qty or 0),
                avg_fill_price=float(o.filled_avg_price or 0),
            )
        except Exception as e:
            return OrderResult(order_id="", status="error", symbol=order.symbol, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        try:
            self._api.cancel_order(order_id)
            return True
        except Exception:
            return False

    async def get_market_data(self, symbol: str) -> MarketData:
        quote = self._api.get_last_quote(symbol)
        trade = self._api.get_last_trade(symbol)
        return MarketData(
            symbol=symbol,
            bid=float(quote.bidprice),
            ask=float(quote.askprice),
            last=float(trade.price),
            volume=int(trade.size),
        )

    async def get_options_chain(self, symbol: str, expiration: str) -> dict:
        # Alpaca options chain via REST
        try:
            chain = self._api.get_options_chain(symbol, expiration_date=expiration)
            return chain
        except Exception:
            return {}
