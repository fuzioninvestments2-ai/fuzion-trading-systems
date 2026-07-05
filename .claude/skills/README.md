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
| 06 | `06-order-execution` | LÍMITE: el bot NO coloca órdenes; traspaso a ejecución MANUAL |
| 07 | `07-position-manager` | LÍMITE: no abre/administra posiciones; se administra el registro |
| 14 | `14-parameter-optimization` | Calibrar/optimizar pesos por resultado real |
| 15 | `15-sentiment-analysis` | Sentimiento/noticias — SOLO Real (en OTC no aplica) |
| 16 | `16-security-encryption` | Secretos (SSID, tokens) — nunca en git |
| 17 | `17-dca-strategy` | LÍMITE: sin DCA/martingala (peligroso en binarias) |
| 18 | `18-grid-trading` | LÍMITE: sin grid (no aplica a binarias) |
| 19 | `19-web-dashboard` | Panel web de SOLO LECTURA, uno por proyecto |
| 20 | `20-deployment` | Lanzadores .bat, robot 24/7, subida a la nube |

Los 20 skills de la lista están creados. Los numerados existen todos (01-20).

## Cómo usarlo (centralizado)
- ¿Ajuste/corrección del **OTC**? → `proyecto-otc` (y de ahí al módulo compartido).
- ¿Ajuste/corrección del **Real**? → `proyecto-real`.
- ¿Cambio técnico de un módulo (indicadores, conexión, tarjeta)? → el skill `0X`.

## Skills de LÍMITE (Fuzion es de SEÑALES, no coloca órdenes)
`06`, `07`, `17`, `18` existen con su nombre exacto, pero **documentan el límite**:
el proyecto es de solo lectura (regla `no negociable` en `CLAUDE.md`), así que esos
skills explican dónde para el bot, por qué, y cómo la señal pasa a **ejecución
MANUAL** del humano. No contienen lógica que coloque órdenes reales. Si se quiere
ejecución automática, es un cambio de propósito que exige confirmación explícita y,
aun así, solo demo + confirmación manual por operación (nunca fuego automático).
