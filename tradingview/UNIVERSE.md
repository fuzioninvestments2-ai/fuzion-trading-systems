# Universo multi-activo — cómo desplegar el bot en muchos símbolos

Una estrategia de Pine corre sobre **un símbolo a la vez** (el del gráfico). Para
cubrir "todos los top", se aplica el **mismo script** a cada gráfico y se crea
**una alerta por símbolo**. Usa el input **"Clase de activo (preset)"** para que
el bot se autoajuste (volatilidad mínima y sesiones) por mercado.

> TradingView Pro+ permite varias alertas simultáneas. Crea una alerta por
> símbolo con el mismo webhook; el JSON incluye `ticker`, así que el ejecutor
> sabe a qué mercado pertenece cada señal.

## Tickers por clase (formato según plataforma)

| Activo | TradingView | yfinance (backtest/optimizer) | Bybit/OKX (cripto) | Preset |
|---|---|---|---|---|
| NVIDIA | NVDA | NVDA | — | Acciones |
| Tesla | TSLA | TSLA | — | Acciones |
| Apple | AAPL | AAPL | — | Acciones |
| Amazon | AMZN | AMZN | — | Acciones |
| Meta | META | META | — | Acciones |
| Google | GOOGL | GOOGL | — | Acciones |
| Netflix | NFLX | NFLX | — | Acciones |
| Microsoft | MSFT | MSFT | — | Acciones |
| Nasdaq 100 | NASDAQ:NDX / QQQ | `^NDX` / QQQ | — | Índices |
| S&P 500 | SP:SPX / SPY | `^GSPC` / SPY | — | Índices |
| Dow | DJ:DJI / DIA | DIA | — | Índices |
| S&P futuro | CME_MINI:ES1! | ES=F | — | Futuros |
| Nasdaq futuro | CME_MINI:NQ1! | NQ=F | — | Futuros |
| Oro | COMEX:GC1! | GC=F | — | Futuros |
| Petróleo | NYMEX:CL1! | CL=F | — | Futuros |
| EUR/USD | FX:EURUSD | EURUSD=X | — | Forex |
| GBP/USD | FX:GBPUSD | GBPUSD=X | — | Forex |
| USD/JPY | FX:USDJPY | USDJPY=X | — | Forex |
| Bitcoin | BINANCE:BTCUSDT | BTC-USD | BTCUSDT | Cripto |
| Ethereum | BINANCE:ETHUSDT | ETH-USD | ETHUSDT | Cripto |
| Solana | BINANCE:SOLUSDT | SOL-USD | SOLUSDT | Cripto |

(Lista completa en `config/universe.yaml`.)

## Recomendaciones por clase

- **Cripto**: 24/7. El preset desactiva sesiones. Más volátil → ATR mínimo alto.
  Scalping rinde mejor aquí si tu spread es bajo.
- **Forex**: se mueve poco en % → ATR mínimo bajo. Opera en solape Londres/NY.
- **Acciones/Índices**: respeta sesión NY (13:00–22:00 GMT). Cuidado con gaps de
  apertura y earnings (úsalo con el filtro de noticias del backend).
- **Futuros**: tendencia limpia; el motor Trend suele ser el mejor.

## Coste realista por clase (configúralo en `strategy()` antes de creer métricas)

| Clase | Comisión aprox | Slippage aprox |
|---|---|---|
| Cripto | 0.075% | 0.05% |
| Forex | 0.008% | 0.01% |
| Acciones | 0.02% | 0.02% |
| Futuros | 0.01% | 0.03% |

> Estos son puntos de partida. **Pon los reales de tu broker.** Un sistema que
> solo es rentable con costes irreales no es rentable.
