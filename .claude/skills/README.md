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

## Cómo usarlo (centralizado)
- ¿Ajuste/corrección del **OTC**? → `proyecto-otc` (y de ahí al módulo compartido).
- ¿Ajuste/corrección del **Real**? → `proyecto-real`.
- ¿Cambio técnico de un módulo (indicadores, conexión, tarjeta)? → el skill `0X`.

## Faltan a propósito: 06 y 07
`06-order-execution` y `07-position-manager` **NO existen** — Fuzion es de
SEÑALES: demo, solo lectura, **NO coloca órdenes**. Automatizar órdenes reales es
lo que este proyecto evita (y el mayor riesgo para el dinero). El `05-protection`
cubre lo sano de "gestión de riesgo": bloquea señales malas, no ejecuta operaciones.
