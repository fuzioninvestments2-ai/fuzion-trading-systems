---
name: 09-backtesting
description: Quantum Trading Core · Simula las últimas 100 señales aplicando el filtro cuántico 90%: cuántas pasan y el win-rate estimado. Úsalo cuando el usuario diga "backtest", "medir aciertos", "win-rate real", "cuántas se filtran".
---

# 09 · Backtesting cuántico

Mide cuántas señales pasarían el filtro del 90% y el win-rate resultante. Honesto:
el bot MIDE su acierto real con su registro; ningún sistema gana siempre.

## `backtest_quantum_system()` → `bot/cuantico.backtest_quantum_system(db, 100)`
Toma las últimas 100 señales RESUELTAS (win/loss), aplica el gate de convergencia
≥90% (reconstruida de la metadata o de los votos) y reporta:
- win-rate ANTES, cuántas FILTRADAS, cuántas PASAN, win-rate ESTIMADO, motivos.
- Demo: 100 señales 39% → filtra 58 → las 42 que pasan quedan en 67%.

También `bot/simular_reglas.py <history.db> 100` (reporte por consola con motivos).

## Aprendizaje sobre historial
- `bot/backtester.py` (evalúa aciertos), `bot/calibration.py` (umbral por ~30 velas),
  `bot/weight_learning.py` (multiplicadores por indicador), `bot/signal_log.py`
  (registra cada señal con su probabilidad/convergencia en la columna `meta`).

## Probar
```bash
python bot/test_backtester.py
python bot/simular_reglas.py fuzion-otc/history.db 100
```
