"""Tests del Risk Manager."""
import pytest
from core.risk_manager import (RiskManager, TradeRequest, RiskDecision,
                                 CircuitBreakerState, MAX_SINGLE_POSITION,
                                 MAX_PORTFOLIO_LEVERAGE, MAX_RISK_PER_TRADE)


def _make_rm():
    return RiskManager({
        "max_risk_per_trade": 0.01,
        "max_portfolio_leverage": 1.25,
        "daily_loss_halt": -0.02,
        "weekly_loss_halt": -0.05,
        "monthly_loss_halt": -0.10,
        "max_drawdown_halt": -0.15,
    })


def test_no_stop_loss_rejected():
    rm = _make_rm()
    req = TradeRequest("SPY", "LONG", 450.0, None, 0.05)
    result = rm.validate_trade(req, 100_000)
    assert result.decision == RiskDecision.REJECTED
    assert "stop loss" in result.rejection_reason.lower()


def test_flat_always_approved():
    rm = _make_rm()
    req = TradeRequest("SPY", "FLAT", 450.0, None, 0.0)
    result = rm.validate_trade(req, 100_000)
    assert result.decision == RiskDecision.APPROVED


def test_valid_trade_approved():
    rm = _make_rm()
    req = TradeRequest("SPY", "LONG", 450.0, 440.0, 0.05)
    result = rm.validate_trade(req, 100_000)
    assert result.decision in (RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED)


def test_circuit_breaker_daily_loss():
    rm = _make_rm()
    rm.record_pnl(-0.025)  # -2.5% > -2% threshold
    assert rm.circuit_breaker in (CircuitBreakerState.HALT_DAY, CircuitBreakerState.HALT_MANUAL)
    req = TradeRequest("SPY", "LONG", 450.0, 440.0, 0.05)
    result = rm.validate_trade(req, 100_000)
    assert result.decision == RiskDecision.REJECTED


def test_max_drawdown_halt():
    rm = _make_rm()
    rm.record_pnl(-0.16)  # -16% > -15% threshold
    assert rm.circuit_breaker == CircuitBreakerState.HALT_MANUAL
    req = TradeRequest("SPY", "LONG", 450.0, 440.0, 0.05)
    result = rm.validate_trade(req, 100_000)
    assert result.decision == RiskDecision.REJECTED
    assert "manual" in result.rejection_reason.lower()


def test_hardcoded_limits_cannot_be_relaxed():
    """Los límites hardcodeados no se pueden relajar vía config."""
    rm = RiskManager({"max_risk_per_trade": 0.99})  # Intentar relajar
    assert rm.max_risk_per_trade <= MAX_RISK_PER_TRADE


def test_max_concurrent_positions():
    rm = _make_rm()
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
    for sym in symbols:
        rm.record_trade(sym, "LONG", 0.05, 100.0, 95.0)
    req = TradeRequest("TSLA", "LONG", 200.0, 190.0, 0.05)
    result = rm.validate_trade(req, 100_000)
    assert result.decision == RiskDecision.REJECTED
