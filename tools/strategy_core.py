"""
Núcleo de estrategia para backtest/optimización (versión Python del QUANT BOT v5).

NO replica el Pine tick a tick; es una versión práctica sobre velas cerradas de
un motor "tendencia + pullback + momentum" con los MISMOS filtros de calidad
(confianza mínima, breakeven, timeout, drawdown diario, bloqueo por objetivo).

Objetivo: medir EXPECTATIVA y DRAWDOWN de un set de parámetros con costes
realistas, para poder optimizar de forma honesta (no para buscar win rate alto).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional

import importlib.util
import pathlib

import numpy as np
import pandas as pd

# Carga Indicators directo del archivo para NO arrastrar core/__init__
# (que importa hmmlearn). El optimizador solo necesita pandas/numpy.
_ind_path = pathlib.Path(__file__).resolve().parent.parent / "core" / "indicators.py"
_spec = importlib.util.spec_from_file_location("fuzion_indicators", _ind_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Indicators = _mod.Indicators


# ---------------------------------------------------------------------------
@dataclass
class StrategyParams:
    # Tendencia / momentum
    ema_fast: int = 9
    ema_slow: int = 20
    sma_trend: int = 200
    rsi_len: int = 14
    adx_len: int = 14
    adx_min: float = 25.0
    atr_len: int = 14
    # Riesgo / salidas
    atr_sl_mult: float = 1.5
    rr: float = 2.0               # TP = rr * riesgo
    breakeven_r: float = 1.0      # mueve SL a entrada tras este múltiplo de R
    timeout_bars: int = 20        # cierre por tiempo si no toca TP/SL
    risk_per_trade: float = 0.01  # 1% del equity por operación
    # Calidad / crecimiento
    min_confidence: float = 60.0  # 0..100
    atr_min_pct: float = 0.10     # volatilidad mínima (% precio)
    min_bars_between: int = 1
    max_loss_streak: int = 3
    cooldown_bars: int = 10
    daily_dd_halt: float = 0.05   # -5% día → parar
    daily_profit_lock: float = 0.03  # +3% día → conservar
    allow_shorts: bool = True
    # Costes (fracción, no %). 0.0007 = 0.07%
    commission: float = 0.0005
    slippage: float = 0.0005

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    symbol: str = ""
    n_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0     # ganancia media por trade en múltiplos de R
    net_return: float = 0.0       # retorno total sobre capital inicial
    max_drawdown: float = 0.0     # 0..1 (positivo)
    sharpe: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    growth_score: float = 0.0
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
def compute_features(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    """Añade indicadores al DataFrame OHLCV (columnas en minúscula)."""
    out = df.copy()
    c, h, l, v = out["close"], out["high"], out["low"], out["volume"]
    out["ema_fast"] = Indicators.ema(c, p.ema_fast)
    out["ema_slow"] = Indicators.ema(c, p.ema_slow)
    out["sma_trend"] = Indicators.sma(c, p.sma_trend)
    out["atr"] = Indicators.atr(h, l, c, p.atr_len)
    out["rsi"] = Indicators.rsi(c, p.rsi_len)
    out["adx"] = Indicators.adx(h, l, c, p.adx_len)
    macd_line, _signal, hist = Indicators.macd(c)
    out["macd_hist"] = hist
    out["vol_ma"] = Indicators.sma(v, 20)
    return out


def _confidence(row, direction: int) -> float:
    """Confluencia de filtros 0..100 (6 factores)."""
    up = direction > 0
    checks = [
        (row["close"] > row["sma_trend"]) if up else (row["close"] < row["sma_trend"]),
        (row["ema_fast"] > row["ema_slow"]) if up else (row["ema_fast"] < row["ema_slow"]),
        row["adx"] > 25,
        (40 < row["rsi"] < 70) if up else (30 < row["rsi"] < 60),
        (row["macd_hist"] > 0) if up else (row["macd_hist"] < 0),
        (row["volume"] > row["vol_ma"]) if not np.isnan(row["vol_ma"]) else True,
    ]
    return 100.0 * sum(1 for x in checks if bool(x)) / len(checks)


def backtest(df: pd.DataFrame, p: StrategyParams, symbol: str = "",
             initial_equity: float = 10000.0) -> BacktestResult:
    """Backtest event-driven sobre velas cerradas. Una posición a la vez."""
    data = compute_features(df, p).dropna()
    if len(data) < 50:
        return BacktestResult(symbol=symbol, params=p.to_dict())

    equity = initial_equity
    equity_curve = [equity]
    peak = equity
    max_dd = 0.0

    pos = 0                     # 0 flat, 1 long, -1 short
    entry = stop = tp = 0.0
    risk_per_unit = 0.0
    units = 0.0
    bars_in_trade = 0
    moved_be = False

    trades_r = []               # resultado de cada trade en múltiplos de R
    last_trade_idx = -10 ** 9
    loss_streak = 0
    cooldown_until = -1

    # Control diario
    cur_day = None
    day_start_eq = equity
    halted_day = False
    locked_day = False

    rows = data.reset_index()
    date_col = rows.columns[0]

    cost = p.commission + p.slippage

    for i, row in rows.iterrows():
        day = pd.Timestamp(row[date_col]).date()
        if day != cur_day:
            cur_day = day
            day_start_eq = equity
            halted_day = False
            locked_day = False

        price = row["close"]
        high = row["high"]
        low = row["low"]
        atr = row["atr"]

        # ---- Gestión de posición abierta ----
        if pos != 0:
            bars_in_trade += 1
            exit_price = None
            # Breakeven
            if not moved_be:
                if pos == 1 and high >= entry + p.breakeven_r * risk_per_unit:
                    stop = max(stop, entry)
                    moved_be = True
                elif pos == -1 and low <= entry - p.breakeven_r * risk_per_unit:
                    stop = min(stop, entry)
                    moved_be = True
            # Stop / TP (stop tiene prioridad: peor caso)
            if pos == 1:
                if low <= stop:
                    exit_price = stop
                elif high >= tp:
                    exit_price = tp
            else:
                if high >= stop:
                    exit_price = stop
                elif low <= tp:
                    exit_price = tp
            # Timeout
            if exit_price is None and bars_in_trade >= p.timeout_bars:
                exit_price = price

            if exit_price is not None:
                gross = (exit_price - entry) * units * pos
                fees = (entry + exit_price) * units * cost
                pnl = gross - fees
                equity += pnl
                r_mult = pnl / (risk_per_unit * units) if risk_per_unit * units > 0 else 0.0
                trades_r.append(r_mult)
                loss_streak = loss_streak + 1 if r_mult < 0 else 0
                if loss_streak >= p.max_loss_streak:
                    cooldown_until = i + p.cooldown_bars
                    loss_streak = 0
                pos = 0
                moved_be = False
                bars_in_trade = 0

        # ---- Actualiza equity diaria / circuit breakers ----
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        equity_curve.append(equity)

        day_change = (equity - day_start_eq) / day_start_eq if day_start_eq > 0 else 0.0
        if day_change <= -p.daily_dd_halt:
            halted_day = True
        if day_change >= p.daily_profit_lock:
            locked_day = True

        # ---- Buscar nueva entrada ----
        if pos != 0 or halted_day or locked_day:
            continue
        if i <= cooldown_until or (i - last_trade_idx) < p.min_bars_between:
            continue
        if np.isnan(atr) or atr <= 0:
            continue
        if atr < price * (p.atr_min_pct / 100.0):
            continue

        long_ok = (row["close"] > row["sma_trend"] and row["ema_fast"] > row["ema_slow"]
                   and row["adx"] > p.adx_min and 40 < row["rsi"] < 70 and row["macd_hist"] > 0)
        short_ok = (p.allow_shorts and row["close"] < row["sma_trend"]
                    and row["ema_fast"] < row["ema_slow"] and row["adx"] > p.adx_min
                    and 30 < row["rsi"] < 60 and row["macd_hist"] < 0)

        direction = 1 if long_ok else (-1 if short_ok else 0)
        if direction == 0:
            continue
        if _confidence(row, direction) < p.min_confidence:
            continue

        risk_per_unit = atr * p.atr_sl_mult
        if risk_per_unit <= 0:
            continue
        risk_cap = equity * p.risk_per_trade
        units = risk_cap / risk_per_unit
        entry = price
        stop = entry - risk_per_unit * direction
        tp = entry + risk_per_unit * p.rr * direction
        pos = direction
        bars_in_trade = 0
        moved_be = False
        last_trade_idx = i

    return _metrics(trades_r, equity_curve, initial_equity, symbol, p, max_dd)


def _metrics(trades_r, equity_curve, initial_equity, symbol, p, max_dd) -> BacktestResult:
    n = len(trades_r)
    if n == 0:
        return BacktestResult(symbol=symbol, params=p.to_dict(), max_drawdown=max_dd)

    arr = np.array(trades_r, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = len(wins) / n
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy_r = arr.mean()
    avg_win_r = wins.mean() if len(wins) else 0.0
    avg_loss_r = losses.mean() if len(losses) else 0.0

    eq = np.array(equity_curve, dtype=float)
    net_return = (eq[-1] - initial_equity) / initial_equity
    rets = np.diff(eq) / eq[:-1]
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0

    # GROWTH SCORE: premia expectativa y volumen estadístico, castiga drawdown.
    # NO premia win rate. Requiere muestra mínima para no fiarse de pocos trades.
    pf_adj = min(profit_factor, 5.0) if np.isfinite(profit_factor) else 5.0
    sample = np.sqrt(min(n, 200))
    growth_score = expectancy_r * sample / (1.0 + max_dd * 5.0)
    if n < 20:
        growth_score *= 0.3   # penaliza muestras pequeñas

    return BacktestResult(
        symbol=symbol, n_trades=n, win_rate=round(win_rate, 4),
        profit_factor=round(pf_adj, 3), expectancy_r=round(expectancy_r, 4),
        net_return=round(net_return, 4), max_drawdown=round(max_dd, 4),
        sharpe=round(sharpe, 3), avg_win_r=round(avg_win_r, 3),
        avg_loss_r=round(avg_loss_r, 3), growth_score=round(growth_score, 4),
        params=p.to_dict(),
    )
