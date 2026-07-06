---
name: 14-parameter-optimization
description: Quantum Trading Core · Ajuste de pesos (15/50/35%) y umbrales (90%) según el rendimiento histórico de la DB. Si el win-rate baja de 60%, sugiere subir el umbral de convergencia. Úsalo cuando el usuario diga "calibrar", "optimizar", "ajustar pesos/umbrales", "que aprenda solo".
---

# 14 · Optimización de parámetros (cuántica)

Afina el Motor Cuántico con datos REALES. Honesto: mejora con datos, no promete el
90-95% (ese es tu manual).

## Qué se calibra (arriba de `bot/cuantico.py` y `bot/validacion_senal.py`)
- **Pesos por grupo** (15/50/35%), **umbral de convergencia** (CONV_MIN=90),
  **umbral de probabilidad** (PROB_MIN=90 / 95 si payout<80), ventana de momentum.
- Regla de auto-sugerencia: si el win-rate (Skill 11) baja de **60%**, subir el
  umbral de convergencia o bajar el peso de los ultra-cortos (más ruido).

## Aprendizaje sobre resultados reales
- `bot/weight_learning.py` (hit-rate por indicador → multiplicador),
  `bot/calibration.py` (umbral por ~30 velas), `bot/auto_optimize.py` (ajuste por
  win-rate; PARKED, activar con cuidado). Solo aprende con ≥15 señales resueltas.
- Flujo: opera unos días → `backtest_quantum_system` (Skill 09) → ajustar umbrales.

## Probar
```bash
python bot/test_weight_learning.py
python bot/test_calibration.py
```
