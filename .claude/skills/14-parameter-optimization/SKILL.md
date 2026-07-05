---
name: 14-parameter-optimization
description: Calibración y optimización de parámetros/pesos a partir de resultados reales (sin colocar órdenes). Úsalo cuando el usuario diga "calibrar", "optimizar", "ajustar pesos", "que aprenda solo", "mejorar la precisión", o al tocar calibration / weight_learning / auto_optimize.
---

# 14 · Optimización de parámetros

Ajusta los pesos de los indicadores según qué tan bien aciertan, midiendo el
resultado REAL. Honesto: mejora con datos, no promete el 90-95% (ese es tu manual).

## Archivos
- `bot/weight_learning.py` — hit-rate por indicador → multiplicador de peso
  (50% acierto = 1.0; ±25% sobre el azar = ±0.5).
- `bot/calibration.py` — recalcula con ~30 velas nuevas (continuo).
- `bot/auto_optimize.py` — ajuste de umbrales por timeframe según win-rate
  (>65% sube, <45% baja, con topes). Está PARKED (no cableado): activar con cuidado.

## Regla
Solo aprende con el bot ENCENDIDO y con ≥15 señales resueltas. Reemplaza (no promedia)
lo aprendido de resultados reales sobre lo del backtest.

## Probar
```bash
python -m bot.test_weight_learning
python -m bot.test_calibration
```
