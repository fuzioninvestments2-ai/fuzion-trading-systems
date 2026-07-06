---
name: 10-monitoring-logging
description: Quantum Trading Core · PANEL visual ASCII de los 9 tiempos (probabilidad + convergencia en vivo), logs y auditoría. Úsalo cuando el usuario diga "el panel", "ver el progreso", "revisar los logs", "auditar los datos", "está trabajando el robot".
---

# 10 · Monitoreo y panel visual

Ver el análisis cuántico y si los datos están sanos, sin apagar nada.

## `display_timeframe_panel(qr, conv)` → `bot/cuantico.display_timeframe_panel(frames)`
Tabla ASCII con los 9 timeframes (5s-15m), su dirección/%, la **probabilidad
cuántica** y la **convergencia logarítmica**, y el veredicto (OPERAR/NO OPERAR con
motivo). Mismo panel que va resumido en la tarjeta de Telegram (Skill 08).

## Archivos y usos
- `bot/progreso.py` — cuánto historial hay acumulado por activo/tiempo:
  ```bash
  python -m bot.progreso            # OTC
  python -m bot.progreso real       # REAL
  ```
- `bot/auditoria.py` — completitud (5 pasadas) y qué falta re-escanear:
  ```bash
  python -m bot.auditoria [real]
  ```
- `bot/signal_log.py` — historial de señales para medir win-rate real (columna
  `meta` con los datos de calidad de cada señal).
- `bot/cuantico.display_timeframe_panel(frames)` — PANEL visual del análisis de los
  9 tiempos (5s-15m) con dirección/%, probabilidad, convergencia y veredicto.
- `bot/simular_reglas.py` / `bot/cuantico.backtest_quantum_system(db)` — reporte:
  cuántas señales se filtran y el win-rate estimado de las que pasan.
- `logs/` — salida de ejecución.

## Robot 24/7 (autónomo)
`ROBOT_AUTO.bat` (OTC) / `ROBOT_REAL.bat`: descargan/acumulan y suben a la nube
solos; si se caen, se REINICIAN. Reinicio interno de la conexión antes de molestar
al usuario (socket "vivo pero mudo").

## Watchdog
Si el historial no crece varias rondas: el acumulador fuerza una reconexión interna;
si aun así no crece, avisa que el SSID caducó (refrescarlo a mano).

## Probar
```bash
python -m bot.test_progreso
python -m bot.test_accumulator
```
