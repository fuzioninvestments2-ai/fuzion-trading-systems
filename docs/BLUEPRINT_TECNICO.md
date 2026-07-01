# 🏎️ Blueprint Técnico Maestro — Bot Pocket Option ("Motor Ferrari")

> Documento que organiza la especificación técnica COMPLETA entregada por el
> usuario (indicadores, estrategias, integración, riesgo, DB, fases, criterios).
> Complementa a `ESPECIFICACION_BOT.md`. **No se borró nada**: aquí está todo
> ordenado + las correcciones necesarias para que funcione en OTC real.

---

## 0. ⚠️ CORRECCIONES Y OBSERVACIONES CRÍTICAS (leer PRIMERO)

Estas son las cosas que, como desarrollador honesto, debo advertirte **antes**
de construir. No invalidan el proyecto, pero cambian cómo lo hacemos:

1. **Ticks vs. Velas (lo más importante).**
   Casi todo el código de indicadores asume un `DataFrame` con columnas
   `open, high, low, close, volume` (velas). Pero en **OTC en vivo solo llega
   el PRECIO tick a tick** — no velas ya hechas. → Necesitamos un módulo nuevo
   **"constructor de velas"** que agrupe ticks en velas M1/M5/M15 antes de que
   MACD, Bollinger, ATR, patrones y volumen puedan funcionar. Es un cimiento
   que la spec no incluía.

2. **El VOLUMEN puede no existir en OTC.**
   Pocket Option OTC normalmente **no da volumen real**. El indicador de volumen
   y el OBV podrían **no ser usables**. Habrá que quitarlos o simularlos, con
   honestidad de que no es volumen real.

3. **Dos formas de login que NO coinciden.**
   - El código de **Selenium** hace login con **email + contraseña** en `po.trade`.
   - El **WebSocket** usa el **SSID** (`42["auth",{"sessionToken":...}]`).
   Hay que **elegir uno**. Además, los selectores de Selenium (nombres de clase
   como `call-button`, `user-balance`) son **suposiciones**: habrá que ajustarlos
   al sitio real, y **pueden cambiar sin aviso**.

4. **`ta-lib` es difícil de instalar en Windows** (requiere compilar C). Mejor
   `pandas-ta` o **nuestros propios indicadores**, que ya están hechos y probados.

5. **No dupliquemos indicadores.** El repo ya tiene `core/indicators.py` (pandas)
   y `indicators/` (streaming, ya validados). Reutilizaremos en vez de recrear.

6. **Los "criterios de éxito" (win rate >65%, etc.) son METAS de backtest**, no
   garantías. Y un buen backtest en OTC **no asegura** resultados en vivo.

7. **Términos de Servicio (TOS).** Automatizar Pocket Option **puede violar sus
   TOS** y derivar en bloqueo de cuenta. Tú mismo lo incluiste en las advertencias.
   Lo hacemos en **DEMO** y bajo tu responsabilidad.

8. **Tamaño real del proyecto.** El plan es de **~40 días** de trabajo. Es un bot
   profesional grande; iremos **módulo a módulo** (tu Regla 1), validando cada uno.

---

## 1. 📁 Estructura de directorios propuesta (de la spec)

```
core/         trading_bot.py · session_manager.py · signal_analyzer.py
strategies/   base · indicator · pattern · support_resistance · oscillate · slide
indicators/   rsi · macd · bollinger · moving_averages · stochastic · atr · volume
integration/  selenium_automation.py · websocket_client.py · api_client.py
risk_management/ risk_manager.py · martingale.py · position_sizing.py
database/     trade_logger.py · statistics.py · database_manager.py
ui/           main_window · config_panel · stats_panel · log_panel · chart_panel
backtesting/  backtester · optimizer · data_loader
utils/        helpers · validators · notifications
```
> Nota: parte de esto ya existe en el repo con otra ubicación (ver mapeo §7).

---

## 2. 📈 Indicadores (7) y su lógica de señal

Cada indicador devuelve `(señal, fuerza)` con señal ∈ {CALL, PUT, HOLD}:

| Indicador | Señal principal | Fuerza |
|-----------|-----------------|--------|
| **RSI(14)** | <30 CALL / >70 PUT (fuerte); 30-40 / 60-70 (moderada) | 0.6–0.8 |
| **MACD(12,26,9)** | Cruce alcista+hist>0 CALL / cruce bajista+hist<0 PUT | 0.6–0.85 |
| **Bollinger(20,2)** | precio ≤ banda inf / %b<0 CALL; ≥ banda sup / %b>1 PUT | 0.6–0.8 |
| **Moving Averages** | tendencia + golden/death cross | 0.75 |
| **Stochastic(14,3)** | <20 + cruce alcista CALL; >80 + cruce bajista PUT | 0.6–0.8 |
| **ATR(14)** | mide VOLATILIDAD (no da señal; filtra) | — |
| **Volumen(20)** | confirma con volumen relativo (⚠️ ver corrección §0.2) | 0.7 |

---

## 3. 🧠 Estrategias (3)

**A) Indicadores múltiples (scoring ponderado).** Pesos:
`macd:3, rsi:2, bollinger:2, moving_averages:2, stochastic:1, volume:1`.
Suma `call_score` vs `put_score`; `confianza = |score| / score_máx`.
Decide si `confianza ≥ min_confidence`.

**B) Patrones de velas japonesas.** Detecta: Hammer, Shooting Star, Bullish/
Bearish Engulfing, Doji, Inverted Hammer, Morning/Evening Star. (⚠️ Requiere
velas OHLC — ver §0.1.)

**C) Soporte / Resistencia.** Encuentra máximos/mínimos locales (lookback 50),
agrupa niveles cercanos, y da señal por proximidad (<0.1% muy cerca, <0.5% cerca).

**Combinación (voting + Stack Methods):**
| Método | Votos requeridos | Confianza mín |
|--------|------------------|---------------|
| conservative | 4 | 80% |
| moderate | 3 | 70% |
| aggressive | 2 | 60% |

---

## 4. 🔌 Integración con Pocket Option (2 métodos)

**Método 1 — Selenium (navegador):** login, seleccionar activo, poner monto,
elegir expiración, clic CALL/PUT, leer balance y velas del DOM/JS.
⚠️ Selectores y URL (`po.trade`) son plantillas a validar; login por email/pass.

**Método 2 — WebSocket:** más rápido; usa SSID; el cliente del repo necesita
corregir el formato de auth (§0.3).

---

## 5. 🛡️ Gestión de riesgo (RiskManager)

- `max_daily_loss = trade_capital * 3`
- `max_consecutive_losses = 5`
- `max_drawdown_percent = 0.20`
- `calculate_position_size`: base 2% del balance × confianza, tope `trade_capital`.
- `check_risk_limits`: corta si se supera pérdida diaria / pérdidas seguidas / drawdown.
- **Martingale:** módulo aparte, con tope de pasos (§ ESPECIFICACION_BOT §7).

---

## 6. 🗄️ Base de datos (SQLite)

Tabla `trades` (timestamp, asset, direction, amount, result, profit, confidence,
strategy, details) y tabla `sessions` (start/end, target, actual_profit, trades,
wins, losses, win_rate). Estadísticas por rango de días.

---

## 7. 🔗 Mapeo con lo YA construido

| Spec | Ya existe | Acción |
|------|-----------|--------|
| indicators/rsi, stochastic | `indicators/*.py` (streaming) + `core/indicators.py` | Reutilizar/adaptar |
| macd, bollinger, atr, MAs | `core/indicators.py` (pandas) | Reutilizar |
| strategies/indicator | `strategy/confluence.py` | Ampliar a scoring+votos |
| integration/websocket | `connection/ws_client.py`, `bot/resilient_pocket_option.py` | Reutilizar |
| risk_management | — | Construir (§5) |
| database/trade_logger | — | Construir (§6) |
| core/trading_bot, session | `bot/otc_bot.py` (base) | Ampliar a sesiones/target |
| constructor de velas | — | **Construir (nuevo, §0.1)** |
| ui/ (PyQt) | — | Construir (fase tardía) |

---

## 8. 🗺️ Plan por fases (de la spec, ~40 días)

1. Configuración inicial · 2. Indicadores · 3. Estrategias · 4. Integración PO ·
5. Gestión de riesgo · 6. Interfaz PyQt · 7. Logging/estadísticas ·
8. Backtesting · 9. Pruebas/optimización · 10. Despliegue (PyInstaller).

---

## 9. 🎯 Criterios de éxito (METAS de backtest, no garantías)

Win rate >65% · Profit factor >1.5 · Max drawdown <20% · 10+ sesiones/día ·
target alcanzado en 80% de sesiones · <2 s por trade · estable 24/7 · UI fluida ·
logging completo · stop-loss funcionando.

---

## 10. ✅ Orden de construcción recomendado (adaptado a la Regla 1)

Priorizando cimientos que faltan y reutilizando lo hecho:

1. **`config.py` + presets** — todos los parámetros (§3 ESPECIFICACION) ajustables.
2. **Constructor de velas** (ticks → M1/M5) — **desbloquea** MACD/Bollinger/ATR/patrones.
3. **Estrategia de scoring + votos (stack methods)** — el corazón de la decisión.
4. **RiskManager + Martingale con tope + stop diario** — protege el capital.
5. **Motor de sesiones** (target_profit / stop / auto_restart / max_sessions).
6. **TradeLogger (SQLite) + estadísticas.**
7. **Integración real** (Selenium o WebSocket, según decisión).
8. **Control Telegram** y luego **UI PyQt**.
9. **Backtesting.**

Cada módulo: comentado (el porqué), robusto, **validado en terminal**, demo primero.
