# Skills de Fuzion — clasificados por proyecto

Son **DOS proyectos separados** que comparten el mismo motor (código en `bot/`):
**(OTC)** y **(Mercado Real / FX)**. Los skills se organizan así:

## 1) Skills POR PROYECTO (lo específico de cada bot)
Aquí vas cuando algo es de UN proyecto (carpeta, cuenta, token, arranque, datos):

| Skill | Proyecto | Carpeta | Bot Telegram |
|-------|----------|---------|--------------|
| `proyecto-otc` | **OTC** | `fuzion-otc` | @fuzion_ale_bot (Fuzion POption OTC) |
| `proyecto-real` | **Mercado Real** | `fuzion-real` | @FuZionFzbot (Fuzion POption FX) |

Cada uno lista SU cuenta (SSID), token, base de datos, datasets, lanzador y reglas.
No se cruzan.

## 2) Skills COMPARTIDOS (el motor, sirve a los dos)
El código es el mismo para ambos; estos skills describen cada módulo. Aquí vas
cuando el problema es técnico (no de un proyecto en concreto):

| # | Skill | Qué cubre |
|---|-------|-----------|
| 01 | `01-api-connection` | Conexión a Pocket Option (websocket, reconexión, SSID) |
| 02 | `02-market-data` | Velas, historial, descarga, datasets, nube, auditoría |
| 03 | `03-indicators` | Los 10 indicadores del trader y su voto |
| 04 | `04-strategy-logic` | Alineación 12 tiempos, ley EMA200-1H, veredicto |
| 05 | `05-protection` | Filtros y barreras (payout, noticias, sesiones, anti-basura) |
| 08 | `08-notifications` | Telegram + tarjeta (chart, panel, hora de entrada) |
| 09 | `09-backtesting` | Backtest y aprendizaje (medir aciertos, calibrar) |
| 10 | `10-monitoring-logging` | Progreso, auditoría, logs, robot 24/7 |
| 11 | `11-database-persistence` | Sqlite: velas, señales, aprendizaje (por bot) |
| 12 | `12-multi-pair-manager` | Muchos pares: watchlist, foco, menú alfabético |
| 13 | `13-multi-timeframe` | Sinfonía de dirección: 12 tiempos, pesos, 7/12 |
| 14 | `14-parameter-optimization` | Calibrar/optimizar pesos por resultado real |
| 16 | `16-security-encryption` | Secretos (SSID, tokens) — nunca en git |
| 20 | `20-deployment` | Lanzadores .bat, robot 24/7, subida a la nube |

## Cómo usarlo (centralizado)
- ¿Ajuste/corrección del **OTC**? → `proyecto-otc` (y de ahí al módulo compartido).
- ¿Ajuste/corrección del **Real**? → `proyecto-real`.
- ¿Cambio técnico de un módulo (indicadores, conexión, tarjeta)? → el skill `0X`.

## Faltan a propósito (Fuzion es de SEÑALES, no coloca órdenes)
Estos módulos de la lista genérica **NO se crean** porque implican OPERAR solo /
poner órdenes reales — justo lo que este proyecto evita (demo, solo lectura) y el
mayor riesgo para el dinero:
- `06-order-execution` — ejecutar órdenes.
- `07-position-manager` — gestionar posiciones abiertas.
- `17-dca-strategy` — promediar comprando (coloca órdenes).
- `18-grid-trading` — rejilla de órdenes automáticas.

El `05-protection` cubre lo sano de "gestión de riesgo": bloquea señales malas.

Otros de la lista, pendientes (no imprescindibles hoy):
- `15-sentiment-analysis` — Fuzion tiene filtro de NOTICIAS (`news_filter`), no
  análisis de sentimiento; se puede adaptar si se quiere.
- `19-web-dashboard` — panel web: sería un desarrollo nuevo (hoy la interfaz es
  Telegram + `bot/progreso`).
