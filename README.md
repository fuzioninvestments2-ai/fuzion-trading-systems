# FUZION Trading Systems — Python Backend

Backend Python para la plataforma de trading automatizado FUZION. Se integra con el frontend web existente vía APIs REST (FastAPI).

---

## Arquitectura

```
┌─────────────────────────────────────┐
│        FUZION Web App (existe)      │
│  Dashboard · Tools Hub · Bot        │
└────────────────┬────────────────────┘
                 │ APIs REST (JSON)
                 ▼
┌─────────────────────────────────────┐
│     PYTHON BACKEND (este repo)      │
│  HMM Engine · 18 Options Systems   │
│  Brokers · Backtesting · FastAPI    │
└─────────────────────────────────────┘
```

---

## Estructura del Proyecto

```
fuzion-trading-systems/
├── main.py                    # Entry point principal
├── requirements.txt
├── setup.py
├── .env.example
├── config/
│   ├── settings.yaml          # Configuración principal
│   └── credentials.yaml.example
│
├── core/                      # Motor central
│   ├── hmm_engine.py          # Gaussian HMM (detección de regímenes)
│   ├── regime_strategies.py   # Orquestador de estrategias por régimen
│   ├── risk_manager.py        # Gestión de riesgo (VETO ABSOLUTO)
│   └── indicators.py          # Biblioteca de indicadores técnicos
│
├── broker/                    # Adaptadores de brokers
│   ├── base_broker.py
│   ├── ibkr_client.py         # Interactive Brokers (TWS/Gateway)
│   ├── alpaca_client.py       # Alpaca (API gratuita)
│   ├── bybit_client.py        # Bybit (crypto, API v5)
│   ├── okx_client.py          # OKX (spot, futures, opciones)
│   ├── pocket_option_client.py # Opciones binarias ⚠️ ALTO RIESGO
│   ├── order_executor.py
│   └── position_tracker.py
│
├── data/                      # Pipeline de datos
│   ├── market_data.py
│   └── feature_engineering.py # 14 features z-scored para HMM
│
├── options/                   # 18 Sistemas de opciones
│   ├── common/                # Módulos compartidos
│   │   ├── chain_fetcher.py   # Cadenas de opciones (yfinance/Polygon)
│   │   ├── greeks_calculator.py # Black-Scholes: Delta/Gamma/Theta/Vega/Rho
│   │   ├── iv_analyzer.py     # IV Rank, Percentile, Term Structure, Skew
│   │   ├── strike_selector.py # Selección óptima de strikes
│   │   ├── position_sizer.py  # Kelly Criterion adaptado para opciones
│   │   └── options_screener.py
│   ├── wheel/                 # The Wheel (CSP → Covered Call)
│   ├── iron_condor/           # Iron Condor
│   ├── credit_spread/         # Bull Put / Bear Call Spreads
│   ├── short_strangle/        # Short Strangle ⚠️ RIESGO INDEFINIDO
│   ├── covered_call/          # Covered Call Optimizer
│   ├── debit_spread/          # Bull Call / Bear Put Spreads
│   ├── momentum/              # Momentum Options Plays
│   ├── leaps/                 # LEAPS & Poor Man's Covered Call
│   ├── straddle_strangle/     # Long Vol (comprar volatilidad)
│   ├── calendar_diagonal/     # Calendar & Diagonal Spreads
│   ├── hedge_manager/         # Portfolio Hedge Manager
│   └── earnings/              # Earnings Play System
│
├── backtest/
│   ├── backtester.py          # Walk-Forward (train 504, test 126 barras)
│   ├── performance.py         # Sharpe, Sortino, Drawdown, etc.
│   └── stress_test.py         # Monte Carlo + crash injection
│
├── api/                       # Servidor FastAPI
│   ├── server.py
│   ├── routes/                # regime, options, backtest, signals, broker
│   └── models/                # Pydantic request/response models
│
├── monitoring/
│   ├── logger.py              # Logs JSON rotativos (10MB, 5 backups)
│   └── alerts.py              # Email / webhook (Discord/Slack/Telegram)
│
├── dashboards/                # Streamlit (opcional)
├── tests/
├── scripts/
├── models/                    # Modelos HMM guardados
├── results/                   # Resultados de backtests
└── logs/
```

---

## Motor HMM — Detección de Regímenes

Usa `hmmlearn.GaussianHMM` con selección de modelo por BIC (3–5 estados, 10 restarts).

**14 features z-scored** (ventana 126 días): returns 1d/5d/21d, volatilidad realizada 10d/21d, volume ratio, precio vs EMA20/EMA50, RSI14, MACD signal, Bollinger %b, Stochastic %K, ADX.

**Regímenes detectados** (ordenados por volatilidad):

| Régimen | Descripción |
|---|---|
| `CRASH` | Volatilidad extrema, correlaciones colapsan |
| `BEAR` | Tendencia bajista sostenida |
| `NEUTRAL` | Mercado lateral, baja volatilidad |
| `BULL` | Tendencia alcista |
| `EUPHORIA` | Rally extremo, posible burbuja |

**Reglas anti-bias:**
- SOLO Forward Algorithm para predicción — **NUNCA Viterbi** (evita look-ahead bias)
- Stability filter: 3 barras de persistencia antes de confirmar cambio de régimen
- Flicker detection: >4 cambios en 20 barras → modo incertidumbre
- Walk-forward: refit cada 5 barras · Mínimo 252 barras para entrenar

---

## Risk Manager — Veto Absoluto

El Risk Manager tiene **poder de veto absoluto** sobre cualquier trade. Los límites hardcodeados **no se pueden relajar** vía configuración, solo apretar.

```python
MAX_SINGLE_POSITION    = 0.50   # 50% del equity máximo por posición
MAX_PORTFOLIO_LEVERAGE = 1.25   # 1.25x máximo
MAX_RISK_PER_TRADE     = 0.01   # 1% del equity por trade
MAX_TOTAL_EXPOSURE     = 0.80   # 80% (20% cash floor)
MAX_CORRELATED_EXPOSURE= 0.30   # 30% en grupo correlacionado
MAX_CONCURRENT_POSITIONS = 5    # 5 posiciones simultáneas
MAX_DAILY_TRADES       = 20
MIN_POSITION_VALUE     = 100.0  # $100 mínimo
```

**Circuit Breakers** (independientes del HMM):

| Umbral | Acción |
|---|---|
| -1% diario | Reducir tamaño al 50% |
| -2% diario | Parar trading por hoy |
| -5% semanal | Parar trading por la semana |
| -10% mensual | Parar trading por el mes |
| -15% drawdown | **PARAR TODO — requiere reset manual** |

---

## 18 Sistemas de Opciones

| # | Sistema | Tipo | Notas |
|---|---|---|---|
| 1 | Wheel | Income | CSP → si asignado → Covered Call → repetir |
| 2 | Iron Condor | Income neutral | IV Rank >25, delta ±0.16, DTE 30-45 |
| 3 | Credit Spread | Direccional | Bull put / Bear call, riesgo definido |
| 4 | Short Strangle | Income ⚠️ | Riesgo indefinido — mín. $50k, hedge obligatorio |
| 5 | Covered Call | Income | Optimizador por régimen e IV environment |
| 6 | Debit Spread | Direccional | Bull call / Bear put, comprar IV baja |
| 7 | Momentum Plays | Direccional | Breakout, Gap&Go, Squeeze, VWAP reclaim |
| 8 | LEAPS / PMCC | Posicional | DTE >365, delta 0.70-0.80, stock replacement |
| 9 | Long Vol | Volatilidad | Straddle/Strangle comprados, IV Rank <20 |
| 10 | Calendar / Diagonal | Theta | Front vs back month, estructura en contango |
| 11 | Hedge Manager | Protección | Protective puts, collars, VIX calls, tail risk |
| 12 | Earnings Play | Eventos | Pre-IV expansion, through-earnings condor, post-direction |

Cada sistema incluye: `*_engine.py` · `portfolio_manager.py` · `journal.py` · `analytics.py`

Todos los sistemas están integrados con el régimen HMM activo para ajustar delta, tamaño y agresividad.

---

## Brokers Soportados

| Broker | Uso | SDK |
|---|---|---|
| Interactive Brokers | Stocks, opciones, futuros | `ib_insync` (TWS 7497 paper / 7496 live) |
| Alpaca | Stocks, opciones | REST + WebSocket, API gratuita |
| Bybit | Crypto perpetual futures | `pybit` API v5 |
| OKX | Spot, futures, opciones crypto | `python-okx` REST + WebSocket |
| Pocket Option | Opciones binarias ⚠️ | WebSocket — **ALTO RIESGO** |

**Paper trading siempre primero** — 30 días mínimo antes de pasar a live.

---

## Backtesting Engine

Walk-forward real (sin look-ahead bias):

- **Training window:** 504 barras (~2 años)
- **Test window:** 126 barras (~6 meses)
- **Step forward:** 63 barras (~3 meses)
- **Costos realistas:** $1 comisión/trade · 0.05% slippage/side

**Métricas reportadas** (siempre Sharpe + max drawdown juntos):
Total return · Sharpe · Sortino · Max drawdown (absoluto y duración) · Win rate · Profit factor · Avg win/loss · Expectancy · Time in market

**Benchmarks obligatorios:** Buy & hold · 200 SMA crossover · Random strategy

**Stress testing:** Monte Carlo (10,000 simulaciones) + inyección de crashes históricos (COVID 2020, Flash Crash 2010, Crisis 2008, VIX explosion Feb 2018)

---

## Servidor FastAPI

```
GET  /api/health
POST /api/regime/analyze          → Análisis HMM del régimen actual
GET  /api/regime/current/{symbol} → Régimen activo para un símbolo
GET  /api/options/chain/{symbol}  → Cadena de opciones completa
POST /api/options/greeks          → Calcular Greeks (Black-Scholes)
GET  /api/options/iv/{symbol}     → IV Rank, Percentile, Skew, Term Structure
POST /api/options/screen          → Screener con criterios
POST /api/options/wheel/scan      → Candidatos Wheel (CSP/CC)
POST /api/options/condor/scan     → Candidatos Iron Condor
POST /api/options/spread/scan     → Candidatos Credit/Debit Spread
POST /api/options/earnings/scan   → Plays de earnings
POST /api/backtest/run            → Ejecutar walk-forward backtest
POST /api/backtest/stress         → Monte Carlo + crash injection
POST /api/signals/generate        → Generar señales de trading
POST /api/broker/connect          → Conectar broker
GET  /api/broker/positions        → Posiciones actuales
POST /api/broker/execute          → Ejecutar trade
GET  /api/broker/account          → Info de cuenta
```

**Formato de respuesta estándar:**
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2026-06-01T12:00:00Z",
    "processing_time_ms": 150,
    "version": "1.0.0"
  },
  "errors": []
}
```

---

## Instalación

### Requisitos

- Python 3.11+
- (Opcional) TWS/IB Gateway para Interactive Brokers

### Setup

```bash
git clone https://github.com/fuzioninvestments2-ai/fuzion-trading-systems.git
cd fuzion-trading-systems

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
cp config/credentials.yaml.example config/credentials.yaml
# Editar con tus credenciales
```

### Levantar el servidor

```bash
python main.py
# o directamente:
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Ejecutar backtest desde CLI

```bash
python scripts/run_backtest.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

### Tests

```bash
pytest tests/ -v --cov=. --cov-report=html
```

---

## Configuración Principal (`config/settings.yaml`)

```yaml
broker:
  paper_trading: true       # SIEMPRE empezar en paper
  primary: "alpaca"         # alpaca | ibkr | bybit | okx

universe:
  symbols: [SPY, QQQ, IWM, AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META]
  timeframe: "1Day"

hmm:
  n_candidates: [3, 4, 5]
  n_init: 10
  min_train_bars: 252
  refit_interval: 5

risk:
  max_risk_per_trade: 0.01
  max_drawdown_halt: -0.15

options:
  data_source: "yfinance"   # o "polygon"
  default_dte_range: [30, 45]
  max_options_allocation: 0.30

backtest:
  train_window: 504
  test_window: 126
  commission_per_trade: 1.00
  slippage_pct: 0.0005

api:
  host: "0.0.0.0"
  port: 8000
```

---

## Dependencias Clave

```
hmmlearn>=0.3.0      # HMM engine
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
ta>=0.10.0           # Indicadores técnicos
yfinance>=0.2.0      # Datos de mercado
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.0.0
ib_insync>=0.9.86    # Interactive Brokers
alpaca-trade-api>=3.0.0
pybit>=5.6.0         # Bybit
python-okx>=0.1.0    # OKX
streamlit>=1.28.0    # Dashboards
plotly>=5.18.0
```

---

## Orden de Construcción

1. **Core** — HMM engine + Risk manager + Strategy orchestrator
2. **Options common** — Chain fetcher, Greeks, IV analyzer, Strike selector, Position sizer
3. **Options systems** — Wheel → Iron Condor → Credit Spread → resto
4. **FastAPI** — Servidor con todos los endpoints
5. **Brokers adicionales** — Bybit, OKX, Pocket Option
6. **Tests** — Suite completa incluyendo anti-look-ahead bias
7. **Dashboards** — Streamlit (opcional)

---

## Reglas Críticas

1. **STOP LOSS OBLIGATORIO** — Sin stop loss = sin trade. Siempre.
2. **Risk Manager tiene VETO ABSOLUTO** — Ninguna estrategia puede sobrepasar los límites
3. **SOLO Forward Algorithm** para HMM — NUNCA Viterbi (look-ahead bias)
4. **Paper trading SIEMPRE primero** — 30 días mínimo antes de live
5. **Walk-forward backtesting** — NUNCA backtest convencional (overfitting)
6. **Backtests honestos** — Sharpe SIEMPRE con max drawdown, sin cherry-picking
7. **Circuit breakers independientes del HMM** — Son la última línea de defensa
8. **Límites hardcodeados NO se pueden relajar** — Solo apretar vía config
9. **Opciones binarias = alto riesgo** — Warning prominente siempre
10. **Short strangles = riesgo indefinido** — Cuenta mínima $50k, hedge obligatorio

---

## Integración con FUZION Web

Este backend se integra con el frontend desplegado en `titan-trading-platfo-ufcgle.abacusai.app`.

CORS configurado para: `https://titan-trading-platfo-ufcgle.abacusai.app` y `http://localhost:3000`.

---

## Seguridad

- Nunca commitear API keys o credenciales al repositorio
- Usar `.env` o un gestor de secretos para credenciales de broker
- Rotar API keys periódicamente
- Permisos mínimos necesarios en cada broker

---

**FUZION Investments** · fuzioninvestments2@gmail.com
