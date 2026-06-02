from fastapi import APIRouter, HTTPException
from datetime import datetime
import time
from api.models.backtest_models import BacktestRequest, StressTestRequest
from data.market_data import MarketData as MktData
from backtest.backtester import WalkForwardBacktester
from backtest.stress_test import StressTester

router = APIRouter()


def _resp(data, t0):
    return {"success": True, "data": data,
            "meta": {"timestamp": datetime.utcnow().isoformat() + "Z",
                     "processing_time_ms": round((time.time() - t0) * 1000),
                     "version": "1.0.0"}, "errors": []}


@router.post("/run")
async def run_backtest(request: BacktestRequest):
    t0 = time.time()
    try:
        md = MktData({})
        bars = md.get_bars_range(request.symbol, request.start, request.end)
        config = {
            "hmm": {"n_candidates": [3, 4], "n_init": 3, "min_train_bars": 252,
                    "refit_interval": 5, "zscore_window": 126},
            "risk": {"max_risk_per_trade": 0.01, "max_drawdown_halt": -0.15},
            "commission_per_trade": 1.0,
            "slippage_pct": 0.0005,
        }
        backtester = WalkForwardBacktester(config)
        result = backtester.run(bars, request.initial_equity)
        perf = result.performance
        return _resp({
            "equity_curve": result.equity_curve.tolist(),
            "trades": [vars(t) for t in result.trades],
            "metrics": {
                "total_return": perf.total_return,
                "cagr": perf.cagr,
                "sharpe_ratio": perf.sharpe_ratio,
                "sortino_ratio": perf.sortino_ratio,
                "max_drawdown": perf.max_drawdown,
                "max_drawdown_duration_days": perf.max_drawdown_duration_days,
                "win_rate": perf.win_rate,
                "profit_factor": perf.profit_factor,
                "expectancy": perf.expectancy,
                "total_trades": perf.total_trades,
            },
            "regime_breakdown": result.regime_breakdown,
            "benchmarks": result.benchmarks,
            "windows": result.windows,
        }, t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stress")
async def stress_test(request: StressTestRequest):
    t0 = time.time()
    try:
        md = MktData({})
        bars = md.get_bars(request.symbol, period="5y")
        config = {
            "hmm": {"n_candidates": [3], "n_init": 3, "min_train_bars": 252},
            "risk": {"max_risk_per_trade": 0.01, "max_drawdown_halt": -0.15},
        }
        backtester = WalkForwardBacktester(config)
        result = backtester.run(bars)
        tester = StressTester()
        mc = tester.monte_carlo([vars(t) for t in result.trades],
                                 request.n_simulations)
        crashes = tester.crash_injection(result.equity_curve,
                                          request.crash_scenarios)
        return _resp({
            "monte_carlo": vars(mc),
            "crash_scenarios": [vars(c) for c in crashes],
        }, t0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
