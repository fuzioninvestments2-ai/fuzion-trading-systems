"""
Walk-Forward Backtester.
Training: 504 barras | Test: 126 barras | Step: 63 barras.
NUNCA mira datos futuros (Forward algorithm only).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import pandas as pd
from core.hmm_engine import HMMEngine
from core.risk_manager import RiskManager, TradeRequest
from core.regime_strategies import RegimeOrchestrator, SignalDirection
from .performance import PerformanceMetrics, PerformanceReport


@dataclass
class BacktestTrade:
    symbol: str
    entry_date: str
    exit_date: str
    direction: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    regime: str
    strategy: str
    commission: float
    slippage: float
    in_market: bool = True


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[BacktestTrade]
    performance: PerformanceReport
    regime_breakdown: dict
    benchmarks: dict
    windows: List[dict] = field(default_factory=list)


class WalkForwardBacktester:
    """
    Walk-forward con ventanas deslizantes.
    Refit HMM en cada ventana de training.
    """
    TRAIN_WINDOW = 504
    TEST_WINDOW = 126
    STEP_FORWARD = 63
    COMMISSION = 1.0
    SLIPPAGE = 0.0005

    def __init__(self, config: dict):
        self._hmm_config = config.get("hmm", {})
        self._risk_config = config.get("risk", {})
        self._commission = config.get("commission_per_trade", self.COMMISSION)
        self._slippage = config.get("slippage_pct", self.SLIPPAGE)
        self._train_window = config.get("train_window", self.TRAIN_WINDOW)
        self._test_window = config.get("test_window", self.TEST_WINDOW)
        self._step = config.get("step_forward", self.STEP_FORWARD)

    def run(self, bars: pd.DataFrame, initial_equity: float = 100_000) -> BacktestResult:
        if len(bars) < self._train_window + self._test_window:
            raise ValueError(f"Datos insuficientes. Necesitas al menos "
                             f"{self._train_window + self._test_window} barras.")

        equity = initial_equity
        equity_curve = []
        all_trades: List[BacktestTrade] = []
        windows = []

        start = self._train_window
        while start + self._test_window <= len(bars):
            train_bars = bars.iloc[start - self._train_window:start]
            test_bars = bars.iloc[start:start + self._test_window]

            # Refit HMM en cada ventana de training
            hmm = HMMEngine(self._hmm_config)
            try:
                hmm.fit(train_bars)
            except Exception:
                start += self._step
                continue

            orchestrator = RegimeOrchestrator({"min_confidence": 0.55})
            orchestrator.setup_strategies(hmm.get_regime_info())
            risk = RiskManager(self._risk_config)
            risk.current_equity = equity / initial_equity

            window_trades, window_equity = self._simulate_window(
                test_bars, hmm, orchestrator, risk, equity
            )

            all_trades.extend(window_trades)
            equity_curve.extend(window_equity)
            equity = window_equity[-1] if window_equity else equity

            windows.append({
                "train_start": str(train_bars.index[0].date()),
                "train_end": str(train_bars.index[-1].date()),
                "test_start": str(test_bars.index[0].date()),
                "test_end": str(test_bars.index[-1].date()),
                "trades": len(window_trades),
                "final_equity": round(equity, 2),
            })

            start += self._step

        if not equity_curve:
            equity_curve = [initial_equity]

        eq_series = pd.Series(equity_curve, name="equity")
        performance = PerformanceMetrics.calculate(
            eq_series, [vars(t) for t in all_trades]
        )

        regime_breakdown = self._regime_breakdown(all_trades)
        benchmarks = {
            "buy_and_hold": round(PerformanceMetrics.buy_and_hold_return(bars), 4),
            "sma200_crossover": round(PerformanceMetrics.sma200_crossover_return(bars), 4),
        }

        return BacktestResult(
            equity_curve=eq_series,
            trades=all_trades,
            performance=performance,
            regime_breakdown=regime_breakdown,
            benchmarks=benchmarks,
            windows=windows,
        )

    def _simulate_window(self, test_bars, hmm, orchestrator, risk, equity):
        trades = []
        equity_values = []
        open_trade = None

        for i in range(len(test_bars)):
            current_bar = test_bars.iloc[:i + 1]
            if len(current_bar) < 30:
                equity_values.append(equity)
                continue

            # Actualizar posición abierta
            if open_trade is not None:
                current_price = float(test_bars["close"].iloc[i])
                # Stop loss check
                if (open_trade["direction"] == "LONG" and
                        current_price <= open_trade["stop_loss"]):
                    pnl = (current_price - open_trade["entry_price"]) * open_trade["qty"]
                    pnl -= self._commission + self._slippage * current_price * open_trade["qty"]
                    equity += pnl
                    trades.append(self._make_trade(open_trade, current_bar.index[-1],
                                                    current_price, pnl, equity))
                    open_trade = None
                # Take profit check
                elif (open_trade.get("take_profit") and
                      open_trade["direction"] == "LONG" and
                      current_price >= open_trade["take_profit"]):
                    pnl = (current_price - open_trade["entry_price"]) * open_trade["qty"]
                    pnl -= self._commission + self._slippage * current_price * open_trade["qty"]
                    equity += pnl
                    trades.append(self._make_trade(open_trade, current_bar.index[-1],
                                                    current_price, pnl, equity))
                    open_trade = None

            # Generar nueva señal si no hay posición
            if open_trade is None:
                try:
                    regime_state = hmm.predict_regime(current_bar)
                    symbol = str(test_bars.index.name or "SYMBOL")
                    signal = orchestrator.generate_signal(symbol, current_bar, regime_state)

                    if signal and signal.direction != SignalDirection.FLAT:
                        req = TradeRequest(
                            symbol=symbol,
                            direction=signal.direction.value,
                            entry_price=signal.entry_price,
                            stop_loss=signal.stop_loss,
                            position_size_pct=signal.position_size_pct,
                            leverage=signal.leverage,
                        )
                        result = risk.validate_trade(req, equity)
                        from core.risk_manager import RiskDecision
                        if result.decision != RiskDecision.REJECTED:
                            qty = (result.approved_size_pct * equity) / signal.entry_price
                            entry_cost = self._commission + self._slippage * signal.entry_price * qty
                            equity -= entry_cost
                            open_trade = {
                                "direction": signal.direction.value,
                                "entry_price": signal.entry_price,
                                "stop_loss": signal.stop_loss,
                                "take_profit": signal.take_profit,
                                "qty": qty,
                                "entry_date": current_bar.index[-1],
                                "regime": signal.regime_name,
                                "strategy": signal.strategy_name,
                            }
                            risk.record_trade(symbol, signal.direction.value,
                                              result.approved_size_pct,
                                              signal.entry_price, signal.stop_loss)
                except Exception:
                    pass

            equity_values.append(equity)

        # Cerrar posición al final de la ventana
        if open_trade is not None and len(test_bars) > 0:
            exit_price = float(test_bars["close"].iloc[-1])
            pnl = (exit_price - open_trade["entry_price"]) * open_trade["qty"]
            pnl -= self._commission
            equity += pnl
            trades.append(self._make_trade(
                open_trade, test_bars.index[-1], exit_price, pnl, equity))
            equity_values[-1] = equity

        return trades, equity_values

    @staticmethod
    def _make_trade(open_trade, exit_date, exit_price, pnl, equity) -> BacktestTrade:
        entry = open_trade["entry_price"]
        qty = open_trade["qty"]
        return BacktestTrade(
            symbol="SYMBOL",
            entry_date=str(open_trade["entry_date"].date() if hasattr(open_trade["entry_date"], "date") else open_trade["entry_date"]),
            exit_date=str(exit_date.date() if hasattr(exit_date, "date") else exit_date),
            direction=open_trade["direction"],
            entry_price=round(entry, 4),
            exit_price=round(exit_price, 4),
            qty=round(qty, 4),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl / (entry * qty) if entry * qty > 0 else 0, 4),
            regime=open_trade.get("regime", ""),
            strategy=open_trade.get("strategy", ""),
            commission=1.0,
            slippage=0.0005,
        )

    @staticmethod
    def _regime_breakdown(trades: List[BacktestTrade]) -> dict:
        regimes = {}
        for t in trades:
            r = t.regime or "unknown"
            if r not in regimes:
                regimes[r] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
            regimes[r]["trades"] += 1
            if t.pnl > 0:
                regimes[r]["wins"] += 1
            regimes[r]["total_pnl"] += t.pnl
        for r in regimes:
            t = regimes[r]["trades"]
            regimes[r]["win_rate"] = round(regimes[r]["wins"] / t, 4) if t > 0 else 0
        return regimes
