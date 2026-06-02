"""Bybit broker adapter — API v5, crypto perpetual futures."""
from __future__ import annotations
import os
from typing import List
from pybit.unified_trading import HTTP
from .base_broker import BaseBroker, AccountInfo, Position, Order, OrderResult, MarketData


class BybitClient(BaseBroker):
    def __init__(self, config: dict):
        super().__init__(config)
        self._api_key = config.get("api_key") or os.getenv("BYBIT_API_KEY", "")
        self._secret = config.get("secret") or os.getenv("BYBIT_SECRET", "")
        testnet = config.get("paper_trading", True)
        self._session = HTTP(
            testnet=testnet,
            api_key=self._api_key,
            api_secret=self._secret,
        )

    async def connect(self) -> bool:
        try:
            self._session.get_wallet_balance(accountType="UNIFIED")
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"Bybit connect error: {e}")

    async def disconnect(self):
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        resp = self._session.get_wallet_balance(accountType="UNIFIED")
        wallet = resp["result"]["list"][0]
        equity = float(wallet.get("totalEquity", 0))
        cash = float(wallet.get("totalAvailableBalance", 0))
        return AccountInfo(
            account_id=wallet.get("accountType", "UNIFIED"),
            equity=equity, cash=cash, buying_power=cash,
            paper_trading=self._paper_trading, currency="USDT",
        )

    async def get_positions(self) -> List[Position]:
        resp = self._session.get_positions(category="linear", settleCoin="USDT")
        result = []
        for p in resp["result"]["list"]:
            if float(p["size"]) == 0:
                continue
            result.append(Position(
                symbol=p["symbol"],
                qty=float(p["size"]),
                avg_price=float(p["avgPrice"]),
                current_price=float(p["markPrice"]),
                unrealized_pnl=float(p["unrealisedPnl"]),
                side=p["side"].lower(),
            ))
        return result

    async def place_order(self, order: Order) -> OrderResult:
        try:
            params = dict(
                category="linear",
                symbol=order.symbol,
                side="Buy" if order.side == "buy" else "Sell",
                orderType="Market" if order.order_type == "market" else "Limit",
                qty=str(order.qty),
            )
            if order.limit_price:
                params["price"] = str(order.limit_price)
            resp = self._session.place_order(**params)
            info = resp["result"]
            return OrderResult(
                order_id=info["orderId"],
                status=info["orderStatus"],
                symbol=order.symbol,
            )
        except Exception as e:
            return OrderResult(order_id="", status="error", symbol=order.symbol, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        try:
            self._session.cancel_order(category="linear", orderId=order_id)
            return True
        except Exception:
            return False

    async def get_market_data(self, symbol: str) -> MarketData:
        resp = self._session.get_tickers(category="linear", symbol=symbol)
        t = resp["result"]["list"][0]
        return MarketData(
            symbol=symbol,
            bid=float(t["bid1Price"]),
            ask=float(t["ask1Price"]),
            last=float(t["lastPrice"]),
            volume=int(float(t["volume24h"])),
        )

    async def get_options_chain(self, symbol: str, expiration: str) -> dict:
        resp = self._session.get_instruments_info(category="option", baseCoin=symbol)
        return {"instruments": resp["result"]["list"], "expiration": expiration}
