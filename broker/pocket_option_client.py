"""
Pocket Option adapter — opciones binarias.
⚠️ ADVERTENCIA: Las opciones binarias son instrumentos de ALTO RIESGO.
Solo para traders experimentados. La mayoría de traders pierden dinero.
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import List
import websocket
from .base_broker import BaseBroker, AccountInfo, Position, Order, OrderResult, MarketData

WARNING = """
╔══════════════════════════════════════════════════════╗
║  ⚠️  ADVERTENCIA — OPCIONES BINARIAS ALTO RIESGO  ⚠️  ║
║  Las opciones binarias son productos de alto riesgo.  ║
║  La mayoría de los inversores minoristas pierden      ║
║  dinero. Solo opere si entiende completamente         ║
║  el producto y puede permitirse perder su inversión.  ║
╚══════════════════════════════════════════════════════╝
"""


class PocketOptionClient(BaseBroker):
    SUPPORTED_TIMEFRAMES = ["1m", "5m", "15m"]

    def __init__(self, config: dict):
        super().__init__(config)
        print(WARNING)
        self._ssid = config.get("ssid") or os.getenv("POCKET_OPTION_SSID", "")
        self._demo = config.get("paper_trading", True)
        self._ws_url = ("wss://demo-api-v3.po.market/socket.io/?EIO=4&transport=websocket"
                        if self._demo else
                        "wss://api-v3.po.market/socket.io/?EIO=4&transport=websocket")
        self._ws = None
        self._balance = 0.0

    async def connect(self) -> bool:
        try:
            self._ws = websocket.create_connection(self._ws_url)
            auth_msg = json.dumps({"action": "auth", "ssid": self._ssid})
            self._ws.send(f"42{auth_msg}")
            await asyncio.sleep(1)
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"PocketOption connect error: {e}")

    async def disconnect(self):
        if self._ws:
            self._ws.close()
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            account_id="pocket_option",
            equity=self._balance,
            cash=self._balance,
            buying_power=self._balance,
            paper_trading=self._paper_trading,
        )

    async def get_positions(self) -> List[Position]:
        return []

    async def place_order(self, order: Order) -> OrderResult:
        # Opciones binarias: buy = call, sell = put
        direction = 1 if order.side == "buy" else 0
        payload = json.dumps({
            "action": "openOrder",
            "asset": order.symbol,
            "amount": order.qty,
            "action_": direction,
            "time": 60,  # 1 minuto por defecto
            "isDemo": 1 if self._demo else 0,
        })
        try:
            self._ws.send(f"42{payload}")
            return OrderResult(
                order_id="pending",
                status="submitted",
                symbol=order.symbol,
            )
        except Exception as e:
            return OrderResult(order_id="", status="error", symbol=order.symbol, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        return False  # Opciones binarias no se cancelan

    async def get_market_data(self, symbol: str) -> MarketData:
        payload = json.dumps({"action": "subscribe", "asset": symbol})
        self._ws.send(f"42{payload}")
        raw = self._ws.recv()
        try:
            data = json.loads(raw[2:])
            price = float(data.get("price", 0))
        except Exception:
            price = 0.0
        return MarketData(symbol=symbol, bid=price, ask=price, last=price, volume=0)

    async def get_options_chain(self, symbol: str, expiration: str) -> dict:
        return {"note": "Pocket Option no soporta cadenas de opciones estándar"}
