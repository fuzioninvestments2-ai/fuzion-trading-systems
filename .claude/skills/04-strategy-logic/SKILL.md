---
name: 04-strategy-logic
description: La lógica de la señal — alineación de 12 temporalidades, ley EMA200-1H, veredicto OPERAR/NO OPERAR, y el análisis profundo multi-tiempo. Úsalo cuando el usuario diga "por qué NO OPERAR", "alineación de tiempos", "la ecuación", "EMA200 de 1H", "cambiar la estrategia", o al tocar deep_analysis / alignment / sistema_signal.
---

# 04 · Lógica de estrategia (alineación + veredicto)

Cómo se decide OPERAR / NO OPERAR. El sistema NO fuerza señales: si faltan datos o
alineación, calla (disciplina y protección, no promesas).

## Sistema del trader
- 12 temporalidades: `[5,10,15,30,60,120,180,300,600,900,1800,3600]`.
- Alineación ponderada (`PESOS_ALINEACION`, suman 100). Mínimo: **7/12 OTC**, **8/12 real**.
- **Ley EMA200-1H**: solo se opera en la dirección del EMA200 de 1H (dirección absoluta).
- Ciclo: Compresión → Acumulación → Saturación → Reversión.

## Archivos
- `bot/alignment.py` — `direccion_timeframe(df, tf)` (regla por tiempo) y
  `evaluar_alineacion(frames, sistema)` (aplica la ley 1H + mínimo).
- `bot/filtros.py` — `veredicto_final(frames, sistema, payout, hay_noticia, hora_est,
  spread)`: alineación + filtros = OPERAR/NO OPERAR con motivo.
- `bot/sistema_signal.py` — arma frames desde el repo y formatea la señal.
- `bot/deep_analysis.py` — motor clásico multi-tiempo (la "ecuación": corto+medio+
  largo) + alineación fractal. `bot/pocket_service.analyze()` lo usa para la
  tarjeta completa (lee historial guardado de TODOS los tiempos).

## Probar
```bash
python -m bot.test_alignment
python -m bot.test_filtros
python -m bot.test_sistema_signal
```
Resultado esperado: en tendencia clara → OPERAR; sin 7/12 o con filtro malo → NO OPERAR.
