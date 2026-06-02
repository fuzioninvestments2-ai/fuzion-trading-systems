"""Métricas de performance — Sharpe, Sortino, Drawdown, etc."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np
import pandas as pd


@dataclass
class PerformanceReport:
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    time_in_market: float
    total_trades: int
    benchmark_returns: dict


class PerformanceMetrics:

    @staticmethod
    def calculate(equity_curve: pd.Series, trades: List[dict],
                  risk_free_rate: float = 0.05) -> PerformanceReport:
        if equity_curve.empty:
            return PerformanceReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {})

        returns = equity_curve.pct_change().dropna()
        total_return = float((equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1)

        n_years = len(equity_curve) / 252
        cagr = float((equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / max(n_years, 0.01)) - 1)

        excess_returns = returns - risk_free_rate / 252
        sharpe = float(excess_returns.mean() / excess_returns.std() * np.sqrt(252)) if excess_returns.std() > 0 else 0.0

        downside = returns[returns < 0]
        sortino = float(excess_returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0.0

        max_dd, max_dd_dur = PerformanceMetrics._max_drawdown(equity_curve)

        wins = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in trades if t.get("pnl", 0) < 0]
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

        in_market = sum(1 for t in trades if t.get("in_market", True))
        time_in_market = in_market / len(trades) if trades else 0.0

        return PerformanceReport(
            total_return=round(total_return, 4),
            cagr=round(cagr, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown=round(max_dd, 4),
            max_drawdown_duration_days=max_dd_dur,
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 4),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            expectancy=round(expectancy, 2),
            time_in_market=round(time_in_market, 4),
            total_trades=len(trades),
            benchmark_returns={},
        )

    @staticmethod
    def _max_drawdown(equity: pd.Series):
        roll_max = equity.cummax()
        drawdown = equity / roll_max - 1
        max_dd = float(drawdown.min())

        # Duration
        in_dd = drawdown < 0
        duration = 0
        current = 0
        for v in in_dd:
            if v:
                current += 1
                duration = max(duration, current)
            else:
                current = 0
        return max_dd, duration

    @staticmethod
    def buy_and_hold_return(bars: pd.DataFrame) -> float:
        return float(bars["close"].iloc[-1] / bars["close"].iloc[0] - 1)

    @staticmethod
    def sma200_crossover_return(bars: pd.DataFrame,
                                 commission: float = 1.0,
                                 slippage: float = 0.0005) -> float:
        close = bars["close"]
        sma200 = close.rolling(200).mean()
        position = (close > sma200).astype(int)
        returns = close.pct_change()
        strategy_returns = position.shift(1) * returns
        # Costos
        trades = position.diff().abs()
        cost_per_trade = (commission / (close * 100)) + 2 * slippage
        strategy_returns -= trades * cost_per_trade
        equity = (1 + strategy_returns.dropna()).cumprod()
        return float(equity.iloc[-1] - 1) if not equity.empty else 0.0
