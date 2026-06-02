"""
Risk Manager — PODER DE VETO ABSOLUTO sobre cualquier trade.
Los límites hardcodeados NO se pueden relajar, solo apretar.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from .hmm_engine import RegimeLabel


# ---------------------------------------------------------------------------
# Límites hardcodeados — NO modificar
# ---------------------------------------------------------------------------
MAX_SINGLE_POSITION = 0.50
MAX_PORTFOLIO_LEVERAGE = 1.25
MAX_RISK_PER_TRADE = 0.01
MAX_TOTAL_EXPOSURE = 0.80
MAX_CORRELATED_EXPOSURE = 0.30
MAX_CONCURRENT_POSITIONS = 5
MAX_DAILY_TRADES = 20
MIN_POSITION_VALUE = 100.0

DAILY_LOSS_HALT = -0.02
DAILY_LOSS_REDUCE = -0.01
WEEKLY_LOSS_HALT = -0.05
MONTHLY_LOSS_HALT = -0.10
MAX_DRAWDOWN_HALT = -0.15


class CircuitBreakerState(Enum):
    OK = "ok"
    REDUCE = "reduce"
    HALT_DAY = "halt_day"
    HALT_WEEK = "halt_week"
    HALT_MONTH = "halt_month"
    HALT_MANUAL = "halt_manual"


class RiskDecision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_REDUCED = "approved_reduced"


@dataclass
class TradeRequest:
    symbol: str
    direction: str          # LONG | SHORT | FLAT
    entry_price: float
    stop_loss: Optional[float]
    position_size_pct: float
    leverage: float = 1.0
    take_profit: Optional[float] = None
    strategy_name: str = ""
    correlation_group: str = ""


@dataclass
class RiskResult:
    decision: RiskDecision
    approved_size_pct: float
    approved_leverage: float
    rejection_reason: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class OpenPosition:
    symbol: str
    direction: str
    size_pct: float
    entry_price: float
    stop_loss: float
    correlation_group: str = ""
    open_time: float = field(default_factory=time.time)


class RiskManager:
    def __init__(self, config: dict):
        # Límites configurables (solo se pueden apretar)
        self.max_risk_per_trade = min(config.get("max_risk_per_trade", 0.01), MAX_RISK_PER_TRADE)
        self.max_portfolio_leverage = min(
            config.get("max_portfolio_leverage", 1.25), MAX_PORTFOLIO_LEVERAGE)
        self.daily_loss_halt = max(config.get("daily_loss_halt", -0.02), DAILY_LOSS_HALT)
        self.weekly_loss_halt = max(config.get("weekly_loss_halt", -0.05), WEEKLY_LOSS_HALT)
        self.monthly_loss_halt = max(config.get("monthly_loss_halt", -0.10), MONTHLY_LOSS_HALT)
        self.max_drawdown_halt = max(config.get("max_drawdown_halt", -0.15), MAX_DRAWDOWN_HALT)

        self.circuit_breaker = CircuitBreakerState.OK
        self.open_positions: List[OpenPosition] = []
        self.daily_trades: int = 0
        self.daily_pnl: float = 0.0
        self.weekly_pnl: float = 0.0
        self.monthly_pnl: float = 0.0
        self.peak_equity: float = 1.0
        self.current_equity: float = 1.0
        self._trade_log: List[dict] = []
        self._last_symbol_direction: Dict[str, tuple] = {}
        self._current_date: date = date.today()

    # ------------------------------------------------------------------
    # Validación principal
    # ------------------------------------------------------------------

    def validate_trade(self, request: TradeRequest, equity: float) -> RiskResult:
        self._check_date_rollover()
        self._update_circuit_breaker()

        warnings: List[str] = []

        # 1. Circuit breaker
        if self.circuit_breaker == CircuitBreakerState.HALT_MANUAL:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              "Circuit breaker MANUAL activo — requiere reset manual")
        if self.circuit_breaker in (CircuitBreakerState.HALT_DAY,
                                    CircuitBreakerState.HALT_WEEK,
                                    CircuitBreakerState.HALT_MONTH):
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              f"Circuit breaker activo: {self.circuit_breaker.value}")

        # 2. FLAT siempre permitido
        if request.direction.upper() == "FLAT":
            return RiskResult(RiskDecision.APPROVED, request.position_size_pct,
                              request.leverage)

        # 3. Stop loss obligatorio
        if request.stop_loss is None or request.stop_loss <= 0:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              "Stop loss obligatorio — sin stop loss no hay trade")

        # 4. Trade count diario
        if self.daily_trades >= MAX_DAILY_TRADES:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              f"Límite diario de trades alcanzado ({MAX_DAILY_TRADES})")

        # 5. Posiciones concurrentes
        if len(self.open_positions) >= MAX_CONCURRENT_POSITIONS:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              f"Máximo de posiciones concurrentes ({MAX_CONCURRENT_POSITIONS})")

        # 6. Duplicados (mismo símbolo+dirección en 60s)
        key = (request.symbol, request.direction)
        if key in self._last_symbol_direction:
            last_time = self._last_symbol_direction[key]
            if time.time() - last_time < 60:
                return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                                  "Trade duplicado detectado (mismo símbolo+dirección en <60s)")

        # 7. Exposición total
        total_exposure = sum(p.size_pct for p in self.open_positions)
        if total_exposure >= MAX_TOTAL_EXPOSURE:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              f"Exposición total máxima alcanzada ({MAX_TOTAL_EXPOSURE:.0%})")

        # 8. Position sizing
        risk_per_share = abs(request.entry_price - request.stop_loss)
        if risk_per_share <= 0:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              "Stop loss igual al precio de entrada")

        risk_budget = equity * self.max_risk_per_trade
        max_shares_by_risk = risk_budget / risk_per_share
        max_position_value = equity * MAX_SINGLE_POSITION
        max_shares_by_position = max_position_value / request.entry_price
        cash_available = equity * (MAX_TOTAL_EXPOSURE - total_exposure)
        max_shares_by_cash = cash_available / request.entry_price

        max_shares = min(max_shares_by_risk, max_shares_by_position, max_shares_by_cash)
        requested_shares = (request.position_size_pct * equity) / request.entry_price
        approved_shares = min(requested_shares, max_shares)

        if approved_shares * request.entry_price < MIN_POSITION_VALUE:
            return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                              f"Tamaño de posición menor al mínimo (${MIN_POSITION_VALUE})")

        approved_size_pct = (approved_shares * request.entry_price) / equity

        # 9. Multiplicador de circuit breaker REDUCE
        if self.circuit_breaker == CircuitBreakerState.REDUCE:
            approved_size_pct *= 0.5
            warnings.append("Circuit breaker REDUCE activo — tamaño reducido al 50%")

        # 10. Gap risk overnight
        gap_risk = 3 * risk_per_share * approved_shares / equity
        if gap_risk > 0.02:
            max_by_gap = (0.02 * equity) / (3 * risk_per_share)
            approved_shares = min(approved_shares, max_by_gap)
            approved_size_pct = (approved_shares * request.entry_price) / equity
            warnings.append(f"Tamaño limitado por gap risk overnight")

        # 11. Correlación con posiciones existentes
        if request.correlation_group:
            group_exposure = sum(
                p.size_pct for p in self.open_positions
                if p.correlation_group == request.correlation_group
            )
            if group_exposure >= MAX_CORRELATED_EXPOSURE:
                return RiskResult(RiskDecision.REJECTED, 0.0, 1.0,
                                  f"Exposición correlacionada máxima alcanzada "
                                  f"({MAX_CORRELATED_EXPOSURE:.0%}) en grupo '{request.correlation_group}'")
            # Correlación alta → mitad tamaño
            if group_exposure >= 0.70 * MAX_CORRELATED_EXPOSURE:
                approved_size_pct *= 0.5
                warnings.append(f"Correlación alta en grupo '{request.correlation_group}' — tamaño reducido")

        # Leverage cap
        approved_leverage = min(request.leverage, MAX_PORTFOLIO_LEVERAGE)

        decision = (RiskDecision.APPROVED_REDUCED
                    if approved_size_pct < request.position_size_pct
                    else RiskDecision.APPROVED)

        self._last_symbol_direction[key] = time.time()
        return RiskResult(decision, approved_size_pct, approved_leverage, warnings=warnings)

    # ------------------------------------------------------------------
    # Estado y circuit breakers
    # ------------------------------------------------------------------

    def record_trade(self, symbol: str, direction: str, size_pct: float,
                     entry_price: float, stop_loss: float,
                     correlation_group: str = "") -> None:
        self.daily_trades += 1
        if direction.upper() != "FLAT":
            self.open_positions.append(OpenPosition(
                symbol=symbol, direction=direction, size_pct=size_pct,
                entry_price=entry_price, stop_loss=stop_loss,
                correlation_group=correlation_group,
            ))

    def record_pnl(self, pnl_pct: float) -> None:
        self.daily_pnl += pnl_pct
        self.weekly_pnl += pnl_pct
        self.monthly_pnl += pnl_pct
        self.current_equity *= (1 + pnl_pct)
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        self._update_circuit_breaker()

    def close_position(self, symbol: str) -> None:
        self.open_positions = [p for p in self.open_positions if p.symbol != symbol]

    def reset_manual(self) -> None:
        self.circuit_breaker = CircuitBreakerState.OK
        self.daily_trades = 0
        self.daily_pnl = 0.0

    def _update_circuit_breaker(self) -> None:
        drawdown = (self.current_equity - self.peak_equity) / self.peak_equity

        if drawdown <= self.max_drawdown_halt:
            self.circuit_breaker = CircuitBreakerState.HALT_MANUAL
        elif self.monthly_pnl <= self.monthly_loss_halt:
            self.circuit_breaker = CircuitBreakerState.HALT_MONTH
        elif self.weekly_pnl <= self.weekly_loss_halt:
            self.circuit_breaker = CircuitBreakerState.HALT_WEEK
        elif self.daily_pnl <= self.daily_loss_halt:
            self.circuit_breaker = CircuitBreakerState.HALT_DAY
        elif self.daily_pnl <= DAILY_LOSS_REDUCE:
            self.circuit_breaker = CircuitBreakerState.REDUCE
        else:
            if self.circuit_breaker == CircuitBreakerState.REDUCE:
                self.circuit_breaker = CircuitBreakerState.OK

    def _check_date_rollover(self) -> None:
        today = date.today()
        if today != self._current_date:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self._current_date = today
            if self.circuit_breaker == CircuitBreakerState.HALT_DAY:
                self.circuit_breaker = CircuitBreakerState.OK

    def status(self) -> dict:
        drawdown = (self.current_equity - self.peak_equity) / self.peak_equity
        return {
            "circuit_breaker": self.circuit_breaker.value,
            "daily_trades": self.daily_trades,
            "daily_pnl_pct": round(self.daily_pnl * 100, 2),
            "weekly_pnl_pct": round(self.weekly_pnl * 100, 2),
            "monthly_pnl_pct": round(self.monthly_pnl * 100, 2),
            "drawdown_pct": round(drawdown * 100, 2),
            "open_positions": len(self.open_positions),
            "total_exposure_pct": round(sum(p.size_pct for p in self.open_positions) * 100, 2),
        }
