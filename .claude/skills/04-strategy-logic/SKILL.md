---
name: 04-strategy-logic
description: Quantum Trading Core · MOTOR CENTRAL — Probabilidad Cuántica y Convergencia Logarítmica sobre los 9 timeframes ponderados; decide OPERAR solo con 90%+. Úsalo cuando el usuario diga "por qué NO OPERAR", "probabilidad", "convergencia", "el motor", "la fórmula".
---

# 04 · Motor Cuántico (núcleo del sistema)

El CORAZÓN. Conecta Datos (02), Indicadores (03) y Riesgo (05). Decide OPERAR solo
si Probabilidad ≥ 90% Y Convergencia ≥ 90%. Código: `bot/cuantico.py`.

## Fórmulas exactas
1. **Pesos por grupo**: Ultra-cortos (5s,10s,15s) = 15% · Cortos (1m,2m,3m,5m) = 50%
   · Medios (10m,15m) = 35%. Peso individual = peso_grupo / nº del grupo.
2. **Probabilidad cuántica** — `calculate_quantum_probability(frames)`:
   `P = |Σ(w_i·s_i·f_i) / Σw_i| · C`  (s_i dirección, f_i fuerza).
   `C` = correlación por nº alineados: 9→1.0, 8→0.89, 7→0.78, <7→0.67.
3. **Convergencia logarítmica** — `calculate_logarithmic_convergence(alineados)`:
   `Conv = ln(1+alineados) / ln(1+9) · 100`  (7/9=90.3%, 8/9=95.4%, 9/9=100%).
4. **Decisión** — `validate_signal_90(frames, datos, payout, hora_utc)`: OPERAR solo
   si convergencia ≥ 90 Y probabilidad ≥ 90 (95 si payout<80) Y no pegado a S/R Y
   win-rate ≥ 60% Y los 9 tiempos con datos Y fuera de 22-02 UTC.

## Calibración (importante y honesto)
La probabilidad LITERAL rinde ~40% en tendencia fuerte (MACD/Estocástico aportan
poca fuerza), así que se usa una probabilidad **calibrada** ligada a la convergencia
(≈97% en 9/9, ≈87% en 7/9) — se conserva `probabilidad_literal` para transparencia.
Umbrales calibrables arriba de `bot/cuantico.py`. Cableado en vivo:
`bot/pocket_service.veredicto_sistema`.

## Probar
```bash
python bot/test_cuantico.py
python bot/simular_reglas.py fuzion-otc/history.db 100   # backtest sobre señales reales
```
