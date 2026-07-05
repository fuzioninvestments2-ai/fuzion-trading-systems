# Skills de Fuzion (por módulo)

Metodología: un skill por módulo, cada uno se entiende y prueba por separado. Así el
trabajo no se satura y se reducen errores. Cada `SKILL.md` mapea a los archivos
REALES del paquete `bot/` y trae cómo probarlo.

## Los skills
| # | Skill | Qué cubre |
|---|-------|-----------|
| 01 | `01-api-connection` | Conexión a Pocket Option (websocket, reconexión, SSID) |
| 02 | `02-market-data` | Velas, historial, descarga, datasets, nube, auditoría |
| 03 | `03-indicators` | Los 10 indicadores del trader y su voto |
| 04 | `04-strategy-logic` | Alineación 12 tiempos, ley EMA200-1H, veredicto |
| 05 | `05-protection` | Filtros y barreras (payout, noticias, sesiones, anti-basura) |
| 08 | `08-notifications` | Bot de Telegram + tarjeta de señal (chart, hora de entrada) |
| 09 | `09-backtesting` | Backtest y aprendizaje (medir aciertos, calibrar) |
| 10 | `10-monitoring-logging` | Progreso, auditoría, logs, robot 24/7 |

## Faltan a propósito: 06 y 07
`06-order-execution` y `07-position-manager` **NO existen** — y no es un olvido.

Fuzion es un bot de **SEÑALES educativas**: demo, **solo lectura, NO coloca
órdenes**. Automatizar la ejecución de órdenes reales y la gestión de posiciones es
justo lo que este proyecto evita (propósito y honestidad no negociables) y es el
punto de mayor riesgo para el dinero. El módulo `05-protection` cubre lo sano de
"gestión de riesgo": bloquea señales malas, no ejecuta operaciones.

Si algún día quieres un bot que opere solo, sería OTRO proyecto distinto, con su
propia decisión consciente de riesgo — no este.
