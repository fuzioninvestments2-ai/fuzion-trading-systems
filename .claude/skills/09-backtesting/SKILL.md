---
name: 09-backtesting
description: Backtest y aprendizaje sobre historial (medir aciertos, calibrar pesos de indicadores) SIN colocar órdenes reales. Úsalo cuando el usuario diga "backtest", "medir aciertos", "calibrar", "aprender de las señales", "win-rate real", o al tocar backtester / calibration / weight_learning / signal_log.
---

# 09 · Backtesting y aprendizaje

Mide qué tan bien acierta el sistema sobre historial y ajusta pesos. Honesto: el
90–95% es la experiencia MANUAL del trader, NO una promesa del bot; el bot mide su
acierto REAL con su registro. Ningún sistema gana siempre.

## Archivos
- `bot/backtester.py` — recorre velas y evalúa si la señal habría acertado
  (CALL gana si la vela de expiración cierra por encima; PUT al revés).
- `bot/calibration.py` — recalcula parámetros con ~30 velas nuevas (continuo).
- `bot/weight_learning.py` — aprende multiplicadores por indicador según resultados.
- `bot/signal_log.py` — registra CADA señal del sistema (dirección, tiempo, activo)
  para medir su win-rate real y calibrar. Anti-duplicado por horizonte.

## Regla
El aprendizaje mide el SISTEMA correcto: `analyze_sistema` guarda SU señal
(registrar=False en el motor viejo), así no se mezcla con el motor clásico.

## Probar
```bash
python -m bot.test_backtester
python -m bot.test_signal_log
```
Resultado esperado: el backtest devuelve aciertos/fallos sobre datos sembrados; el
log guarda y no duplica.
