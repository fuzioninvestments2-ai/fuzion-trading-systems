"""Calendar Spread y Diagonal Spread engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

from options.common.chain_models import OptionContract


@dataclass
class CalendarLeg:
    contract: OptionContract
    action: str         # "buy" | "sell"
    quantity: int


@dataclass
class CalendarSpread:
    symbol: str
    strategy: str       # "calendar" | "diagonal"
    option_type: str
    strike_front: float
    strike_back: float
    expiry_front: str
    expiry_back: str
    legs: List[CalendarLeg]
    net_debit: float
    max_profit_estimate: float
    theta_capture_zone: tuple
    vega_exposure: float
    ideal_exit_dte: int = 7


@dataclass
class CalendarSignal:
    symbol: str
    strategy: str
    net_debit: float
    spread: CalendarSpread
    regime_label: str
    confidence: float
    notes: str = ""


class CalendarEngine:
    """
    Calendar/Diagonal spreads. Apropiado en NEUTRAL con term structure contango.
    Vende front-month, compra back-month.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.min_iv_contango = self.config.get("min_iv_contango", 0.02)

    def build_calendar(
        self,
        symbol: str,
        spot: float,
        front_contract: OptionContract,
        back_contract: OptionContract,
        quantity: int = 1,
    ) -> Optional[CalendarSpread]:
        if front_contract.strike != back_contract.strike:
            return None
        if front_contract.implied_volatility is None or back_contract.implied_volatility is None:
            return None
        iv_diff = back_contract.implied_volatility - front_contract.implied_volatility
        if iv_diff < self.min_iv_contango:
            return None

        net_debit = back_contract.ask - front_contract.bid
        if net_debit <= 0:
            return None

        vega = (back_contract.implied_volatility - front_contract.implied_volatility) * spot * 0.01
        theta_zone = (spot * 0.97, spot * 1.03)

        legs = [
            CalendarLeg(front_contract, "sell", quantity),
            CalendarLeg(back_contract, "buy", quantity),
        ]

        return CalendarSpread(
            symbol=symbol, strategy="calendar",
            option_type=front_contract.option_type,
            strike_front=front_contract.strike, strike_back=back_contract.strike,
            expiry_front=front_contract.expiration, expiry_back=back_contract.expiration,
            legs=legs, net_debit=net_debit,
            max_profit_estimate=net_debit * 0.8,
            theta_capture_zone=theta_zone, vega_exposure=vega,
        )

    def build_diagonal(
        self,
        symbol: str,
        spot: float,
        front_contract: OptionContract,
        back_contract: OptionContract,
        quantity: int = 1,
    ) -> Optional[CalendarSpread]:
        if front_contract.implied_volatility is None or back_contract.implied_volatility is None:
            return None
        net_debit = back_contract.ask - front_contract.bid
        if net_debit <= 0:
            return None

        vega = (back_contract.implied_volatility - front_contract.implied_volatility) * spot * 0.01
        theta_zone = (min(front_contract.strike, back_contract.strike) * 0.98,
                      max(front_contract.strike, back_contract.strike) * 1.02)

        legs = [
            CalendarLeg(front_contract, "sell", quantity),
            CalendarLeg(back_contract, "buy", quantity),
        ]

        return CalendarSpread(
            symbol=symbol, strategy="diagonal",
            option_type=front_contract.option_type,
            strike_front=front_contract.strike, strike_back=back_contract.strike,
            expiry_front=front_contract.expiration, expiry_back=back_contract.expiration,
            legs=legs, net_debit=net_debit,
            max_profit_estimate=net_debit * 0.6,
            theta_capture_zone=theta_zone, vega_exposure=vega,
        )

    def should_close(self, spread: CalendarSpread, dte_front: int, current_pnl: float) -> bool:
        if dte_front <= spread.ideal_exit_dte:
            return True
        if current_pnl >= spread.net_debit * 0.8:
            return True
        if current_pnl <= -spread.net_debit * 0.5:
            return True
        return False
