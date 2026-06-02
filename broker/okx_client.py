"""OKX broker adapter — spot, futures, opciones crypto."""
from __future__ import annotations
import os
from typing import List
import okx.Trade as TradeAPI
import okx.Account as AccountAPI
import okx.MarketData as MarketAPI
from .base_broker import BaseBroker, AccountInfo, Position, Order, OrderResult, MarketData


class OKXClient(BaseBroker):
    def __init__(self, config: dict):
        super().__init__(config)
        self._api_key = config.get("api_key") or os.getenv("OKX_API_KEY", "")
        self._secret = config.get("secret") or os.getenv("OKX_SECRET", "")
        self._passphrase = config.get("passphrase") or os.getenv("OKX_PASSPHRASE", "")
        flag = "1" if config.get("paper_trading", True) else "0"
        self._trade = TradeAPI.TradeAPI(self._api_key, self._secret, self._passphrase,
                                        False, flag)
        self._account = AccountAPI.AccountAPI(self._api_key, self._secret, self._passphrase,
                                              False, flag)
        self._market = MarketAPI.MarketAPI(flag=flag)

    async def connect(self) -> bool:
        try:
            self._account.get_account_balance()
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"OKX connect error: {e}")

    async def disconnect(self):
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        resp = self._account.get_account_balance()
        details = resp["data"][0]["details"]
        usdt = next((d for d in details if d["ccy"] == "USDT"), {})
        equity = float(usdt.get("eq", 0))
        cash = float(usdt.get("availBal", 0))
        return AccountInfo(
            account_id="OKX", equity=equity, cash=cash,
            buying_power=cash, paper_trading=self._paper_trading, currency="USDT",
        )

    async def get_positions(self) -> List[Position]:
        resp = self._account.get_positions()
        result = []
        for p in resp.get("data", []):
            qty = float(p.get("pos", 0))
            if qty == 0:
                continue
            result.append(Position(
                symbol=p["instId"],
                qty=abs(qty),
                avg_price=float(p.get("avgPx", 0)),
                current_price=float(p.get("markPx", 0)),
                unrealized_pnl=float(p.get("upl", 0)),
                side="long" if qty > 0 else "short",
            ))
        return result

    async def place_order(self, order: Order) -> OrderResult:
        try:
            resp = self._trade.place_order(
                instId=order.symbol,
                tdMode="cash",
                side="buy" if order.side == "buy" else "sell",
                ordType="market" if order.order_type == "market" else "limit",
                sz=str(order.qty),
                px=str(order.limit_price) if order.limit_price else "",
            )
            data = resp["data"][0]
            return OrderResult(
                order_id=data["ordId"],
                status=data["sCode"],
                symbol=order.symbol,
            )
        except Exception as e:
            return OrderResult(order_id="", status="error", symbol=order.symbol, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        try:
            self._trade.cancel_order(ordId=order_id)
            return True
        except Exception:
            return False

    async def get_market_data(self, symbol: str) -> MarketData:
        resp = self._market.get_ticker(instId=symbol)
        t = resp["data"][0]
        return MarketData(
            symbol=symbol,
            bid=float(t["bidPx"]),
            ask=float(t["askPx"]),
            last=float(t["last"]),
            volume=int(float(t["vol24h"])),
        )

    async def get_options_chain(self, symbol: str, expiration: str) -> dict:
        resp = self._market.get_instruments(instType="OPTION", uly=symbol)
        return {"instruments": resp.get("data", []), "expiration": expiration}
