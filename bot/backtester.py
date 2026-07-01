"""
bot/backtester.py
=================
Motor de BACKTESTING: mide cómo se comporta la estrategia sobre una serie de
velas ya conocida. Sirve para CALIBRAR (encontrar buenos umbrales) antes de
arriesgar nada.

⚠️ HONESTIDAD: un backtest mide el pasado sobre ESOS datos. NO predice el futuro
ni garantiza ganancias, y en OTC (precios sintéticos del bróker) hay que tomarlo
con más cautela todavía. Es una herramienta de diagnóstico, no una promesa.

Modelo de opción binaria:
  - En el índice i, si hay señal, se "abre" la operación.
  - En i + `expiry_horizon` velas se mira el resultado:
      CALL gana si close sube; PUT gana si close baja.
  - Ganar suma `amount * payout`; perder resta `amount`.
"""

from bot.scoring_strategy import ScoringStrategy, CALL, PUT, HOLD


def backtest(cfg, candles_df, expiry_horizon=1, amount=1.0, payout=0.92,
             min_history=210):
    """
    Ejecuta la estrategia sobre `candles_df` (DataFrame OHLC en orden temporal).

    `min_history`: nº mínimo de velas antes de empezar a operar (para que los
    indicadores lentos —SMA200— tengan datos). Por defecto 210.

    Devuelve un dict con métricas honestas (siempre incluye drawdown).
    """
    strat = ScoringStrategy(cfg)
    n = len(candles_df)

    wins = losses = ties = 0
    gross_profit = 0.0     # suma de ganancias (para profit factor)
    gross_loss = 0.0       # suma de pérdidas (valor absoluto)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    signals = 0

    for i in range(min_history, n - expiry_horizon):
        window = candles_df.iloc[: i + 1]          # datos hasta la vela i
        signal, conf, _ = strat.analyze(window)
        if signal not in (CALL, PUT):
            continue

        signals += 1
        entry = float(candles_df["close"].iloc[i])
        exit_ = float(candles_df["close"].iloc[i + expiry_horizon])

        if entry == exit_:
            ties += 1
            continue                               # empate: ni gana ni pierde

        won = (exit_ > entry) if signal == CALL else (exit_ < entry)
        if won:
            wins += 1
            profit = amount * payout
            gross_profit += profit
            equity += profit
        else:
            losses += 1
            gross_loss += amount
            equity -= amount

        # Drawdown: mayor caída desde el pico de equity.
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    decided = wins + losses
    win_rate = (wins / decided) if decided else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    return {
        "signals": signals,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": round(win_rate, 4),
        "net_profit": round(equity, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "max_drawdown": round(max_drawdown, 2),
    }


def sweep_confidence(cfg, candles_df, valores=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
                     **kwargs):
    """
    Prueba varios umbrales de confianza y devuelve las métricas de cada uno.
    Útil para CALIBRAR: ver cómo cambian nº de señales y win rate según el
    umbral (más alto = menos señales pero, en teoría, más selectivas).
    """
    import copy
    resultados = {}
    for v in valores:
        c = copy.copy(cfg)
        c.min_confidence = v               # override solo del umbral
        resultados[v] = backtest(c, candles_df, **kwargs)
    return resultados
