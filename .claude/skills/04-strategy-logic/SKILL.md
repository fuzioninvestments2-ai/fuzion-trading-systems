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

## Motor de decisión (fórmula) + PUERTA DE CALIDAD
- `bot/lectura_tiempo.py` — `leer_tiempo(df, tf, sistema)`: dirección de cada tiempo
  con SU regla + el MOVIMIENTO real reciente (`momentum`), y fuerza = indicadores
  que confirman.
- `bot/formula.py` — `calcular_danza(frames, sistema, tf_operar)`: score continuo
  (dirección×fuerza×peso por PROXIMIDAD al tiempo operado + momentum + zona S/R).
  **La ENTRADA la manda el tiempo operado**; el conjunto solo confirma. Si el
  conjunto va en contra del tiempo operado → NO OPERAR.
- `bot/validacion_senal.py` — **`validate_signal(datos)`**: PUERTA FINAL estricta.
  Aunque la fórmula diga OPERAR, si CUALQUIER regla falla → NO OPERAR con el motivo
  EXACTO. Reglas (no negociables):
  1. Timeframes completos (no operar si faltan tiempos).
  2. Alineación ≥ **80%**.
  3. Win-rate histórico ≥ **60%** (una vez hay ≥10 señales medidas).
  4. Umbral aprendido ≥ **25%**.
  5. Indicadores (RSI/Estocástico/MACD/Bandas) ≥ **60%**; nada en 45-55% (ruido).
  6. Precio a ≥ **15 pips** de soporte/resistencia.
  7. Confirmación por tiempo: cortos/medios ≥ 60%, largos (1h+) ≥ 70%.
  Umbrales calibrables al inicio de `validacion_senal.py`.

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
python bot/test_alignment.py
python bot/test_formula.py
python bot/test_validacion_senal.py
```
Resultado esperado: tendencia clara + reglas de calidad OK → OPERAR; conflicto con
el tiempo operado, alineación <80%, indicador en ruido, pegado a S/R → NO OPERAR
con el motivo exacto.

## Simular las reglas sobre señales reales
```bash
python bot/simular_reglas.py fuzion-otc/history.db 100
```
Reporta: win-rate antes, cuántas se filtran y el win-rate estimado de las que pasan.
