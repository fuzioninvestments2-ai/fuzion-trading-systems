"""Entry point principal de FUZION Trading Systems."""
import argparse
import asyncio
import sys
import yaml
from pathlib import Path


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_api(config: dict):
    import uvicorn
    api_cfg = config.get("api", {})
    uvicorn.run(
        "api.server:app",
        host=api_cfg.get("host", "0.0.0.0"),
        port=api_cfg.get("port", 8000),
        reload=False,
    )


def run_backtest(symbol: str, start: str, end: str, config: dict):
    from data.market_data import MarketData
    from backtest.backtester import WalkForwardBacktester

    print(f"\n[FUZION] Ejecutando backtest: {symbol} {start} → {end}")
    md = MarketData({})
    bars = md.get_bars_range(symbol, start, end)
    print(f"[FUZION] Barras obtenidas: {len(bars)}")

    backtester = WalkForwardBacktester(config.get("backtest", {}))
    result = backtester.run(bars)
    perf = result.performance

    print(f"\n{'='*50}")
    print(f"RESULTADOS DE BACKTEST — {symbol}")
    print(f"{'='*50}")
    print(f"Total Return:      {perf.total_return:.2%}")
    print(f"CAGR:              {perf.cagr:.2%}")
    print(f"Sharpe Ratio:      {perf.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:     {perf.sortino_ratio:.2f}")
    print(f"Max Drawdown:      {perf.max_drawdown:.2%}")
    print(f"Win Rate:          {perf.win_rate:.2%}")
    print(f"Profit Factor:     {perf.profit_factor:.2f}")
    print(f"Total Trades:      {perf.total_trades}")
    print(f"\nBenchmarks:")
    for k, v in result.benchmarks.items():
        print(f"  {k}: {v:.2%}")
    print(f"{'='*50}\n")


def run_live(config: dict):
    """Loop principal de trading en vivo (paper trading)."""
    import schedule
    import time
    from data.market_data import MarketData
    from core.hmm_engine import HMMEngine
    from core.risk_manager import RiskManager
    from core.regime_strategies import RegimeOrchestrator
    from monitoring.logger import FuzionLogger
    from monitoring.alerts import AlertManager

    logger = FuzionLogger(config.get("log_dir", "./logs"))
    alerts = AlertManager(config.get("alerts", {}))
    md = MarketData({})
    hmm_cfg = config.get("hmm", {})
    risk_cfg = config.get("risk", {})
    universe = config.get("universe", {}).get("symbols", ["SPY"])

    logger.log_info("FUZION Trading Systems arrancando", mode="live" if not config.get("broker", {}).get("paper_trading") else "paper")

    hmm = HMMEngine(hmm_cfg)
    risk = RiskManager(risk_cfg)
    orchestrator = RegimeOrchestrator({"min_confidence": 0.55})

    def trading_cycle():
        for symbol in universe:
            try:
                bars = md.get_bars(symbol, period="2y")
                if not hmm.is_trained():
                    hmm.fit(bars)
                    orchestrator.setup_strategies(hmm.get_regime_info())
                state = hmm.predict_regime(bars)
                signal = orchestrator.generate_signal(symbol, bars, state)
                logger.log_regime(state.current_regime.label.value,
                                   state.regime_probability, symbol)
                if signal:
                    logger.log_info(f"Señal generada: {signal.direction.value} {symbol}",
                                     confidence=signal.confidence,
                                     reasoning=signal.reasoning)
            except Exception as e:
                logger.log_error(f"Error en ciclo de trading para {symbol}: {e}")

    schedule.every().day.at("09:35").do(trading_cycle)
    schedule.every().day.at("16:00").do(
        lambda: alerts.daily_summary(0, 0.0, 100_000))

    logger.log_info("Loop de trading iniciado. Esperando horario de mercado...")
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="FUZION Trading Systems")
    parser.add_argument("mode", choices=["api", "backtest", "live"],
                        help="Modo de operación")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.mode == "api":
        run_api(config)
    elif args.mode == "backtest":
        run_backtest(args.symbol, args.start, args.end, config)
    elif args.mode == "live":
        run_live(config)


if __name__ == "__main__":
    main()
