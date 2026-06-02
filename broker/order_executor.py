"""Ejecutor de órdenes con validación de risk manager."""
from __future__ import annotations
import asyncio
from typing import Optional
from .base_broker import BaseBroker, Order, OrderResult
from core.risk_manager import RiskManager, TradeRequest, RiskDecision


class OrderExecutor:
    def __init__(self, broker: BaseBroker, risk_manager: RiskManager):
        self._broker = broker
        self._risk = risk_manager

    async def execute_signal(self, symbol: str, direction: str, entry_price: float,
                             stop_loss: float, position_size_pct: float,
                             equity: float, leverage: float = 1.0,
                             take_profit: Optional[float] = None,
                             strategy_name: str = "",
                             correlation_group: str = "") -> dict:
        request = TradeRequest(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            position_size_pct=position_size_pct,
            leverage=leverage,
            take_profit=take_profit,
            strategy_name=strategy_name,
            correlation_group=correlation_group,
        )

        result = self._risk.validate_trade(request, equity)

        if result.decision == RiskDecision.REJECTED:
            return {"status": "rejected", "reason": result.rejection_reason}

        qty = (result.approved_size_pct * equity) / entry_price

        order = Order(
            symbol=symbol,
            qty=round(qty, 2),
            side="buy" if direction.upper() == "LONG" else "sell",
            order_type="limit",
            limit_price=round(entry_price, 4),
            time_in_force="day",
        )

        order_result = await self._broker.place_order(order)

        if order_result.status not in ("error",):
            self._risk.record_trade(
                symbol=symbol,
                direction=direction,
                size_pct=result.approved_size_pct,
                entry_price=entry_price,
                stop_loss=stop_loss,
                correlation_group=correlation_group,
            )

        return {
            "status": order_result.status,
            "order_id": order_result.order_id,
            "symbol": symbol,
            "qty": qty,
            "approved_size_pct": result.approved_size_pct,
            "warnings": result.warnings,
            "error": order_result.error,
        }
