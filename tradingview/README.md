# QUANT BOT v5 — Estrategia TradingView (Pine Script v5)

`quant_bot_v5.pine` es un **generador de señales autónomo** para TradingView que
opera intra-vela y emite alertas JSON por webhook hacia un ejecutor externo
(Cornix, 3Commas, Telegram o el backend Python de este repo).

> ⚠️ Para dinero real **empieza siempre en paper / demo** y valida con backtest
> + replay antes de conectar el webhook a una cuenta con fondos.

---

## Qué hace

Tres motores en paralelo, con **un solo trade abierto a la vez** (prioridad
Tendencia > Swing > Scalping):

| Motor | TF objetivo | Entrada (resumen) | Gestión |
|---|---|---|---|
| **1 · Scalping** | 1m–5m | VWAP + EMA9>20 + SuperTrend(15m) + (RSI/Williams%R/CCI) + Stoch + volumen + ATR | SL 0.8×ATR · TP1 0.3% · TP2 0.6% · trailing SAR · timeout 5 velas |
| **2 · Swing** | 15m–1h | SMA200 + ADX/DMI(1h) + RSI(1h) Cardwell + pullback EMA20 + MACD + MFI + OBV | SL 2×ATR · TP1 3R · TP2 5R · breakeven 1.5R · trailing SuperTrend |
| **3 · Tendencia** | 1h–4h–1D | SMA200 + ADX(4h) + Ichimoku + Donchian(Turtle) + Ultimate Osc + Fib golden zone | SL 3×ATR(D) · TP ext. Fib 1.618 · trailing 3×ATR |

**Indicadores integrados:** EMA/SMA, MACD, RSI (modo Cardwell + anti-embedded),
Estocástico, Williams %R, CCI (Zero-Line-Reject), Bollinger, Keltner, Squeeze,
Donchian, ATR, Parabolic SAR, SuperTrend, ADX/DMI, Volumen, OBV, VWAP, MFI, CMF,
Ichimoku, Awesome Oscillator, TRIX, Ultimate Oscillator, Fibonacci (zona dorada
+ extensiones) y Pivots (clásicos + Camarilla).

**Extras:** sizing por riesgo/ATR + Kelly fraccionado, drawdown diario (blando
50% / duro halt), filtro de "noticias" por anomalía volumen+rango (pausa 3
velas), sesiones Londres/NY con cierre anticipado, panel de control y confianza
0–100 por confluencia.

---

## Instalación

1. TradingView → **Pine Editor** → pega el contenido de `quant_bot_v5.pine`.
2. **Add to chart**. Ábrelo en el símbolo y timeframe base (1m–5m para scalping).
3. Ajusta inputs por grupos (A–H). Activa/desactiva motores en el grupo **0**.
4. **Strategy Tester** para backtest. Usa **Bar Replay** para validar intra-vela.

> Requiere plan con `calc_on_every_tick` y suficientes llamadas
> `request.security` (el script usa 5; el límite habitual es 40).

---

## Alertas / Webhook

Crea una alerta sobre la estrategia:

- Condición: **QUANT BOT v5** → *"Any alert() function call"* (o *Order fills*).
- En el mensaje, deja `{{strategy.order.alert_message}}` o usa el `alert()` interno.
- URL del webhook = tu ejecutor (Cornix / 3Commas / Telegram / backend FUZION).

**Formato de entrada (JSON):**

```json
{
  "version": "5.0", "bot": "QBv5", "timestamp": "...",
  "ticker": "BTCUSDT", "action": "buy", "side": "long",
  "engine": "swing", "confidence": 83,
  "entry": { "price": "...", "type": "market" },
  "risk": { "stop_loss": "...", "take_profit_1": "...", "take_profit_2": "...", "risk_percent": 1.0 },
  "signals": { "adx": 32, "rsi": 45, "macd": "bullish", "ichimoku": "above_cloud", "vwap_side": "above", "cmf": 0.12 }
}
```

**Cierre parcial / total:**

```json
{ "version": "5.0", "bot": "QBv5", "action": "close_percent", "percent": 45, "ticker": "BTCUSDT" }
{ "version": "5.0", "bot": "QBv5", "action": "close", "percent": 100, "ticker": "BTCUSDT" }
```

---

## Integración con el backend FUZION

El JSON puede apuntar a un endpoint del backend (FastAPI) que reciba la señal,
la pase por el **Risk Manager** (veto absoluto) y la ejecute vía el broker
correspondiente (`broker/*_client.py`). El campo `confidence` y los `signals`
permiten al backend cruzar la señal con el régimen HMM antes de ejecutar.

---

## Anti-repaint y honestidad de backtest

- Todas las confirmaciones de TF superior usan la **vela cerrada** (`[1]`) y
  `lookahead=barmerge.lookahead_off`.
- `calc_on_every_tick=true` permite scalping en tiempo real; en histórico cada
  vela se evalúa una vez confirmada.
- Comisión 0.075% y slippage 3 ticks ya configurados en `strategy()`. Ajústalos
  a tu broker real antes de fiarte de las métricas.

---

## Limitaciones honestas (lo que Pine NO puede hacer)

- **No lee noticias reales** → se usa un *proxy* por anomalía de volatilidad.
  Para noticias reales (NewsAPI/Benzinga + FinBERT/VADER) hay que hacerlo en el
  backend Python y enviar un filtro/override al webhook.
- **No ejecuta ML pesado** (LSTM/XGBoost) → aquí se aproxima con osciladores
  adaptativos y multi-TF. El ML real vive en el backend (`core/`, `models/`).
- La ejecución final (slippage, fills, latencia) depende de tu broker/conector.
