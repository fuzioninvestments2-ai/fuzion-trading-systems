---
name: 03-indicators
description: Los 10 indicadores del sistema del trader (EMA 8/20/50/200, Estocástico 5,3,3, Bollinger 14/1.02, Donchian 20, RSI 5, MACD 12,26,9, Soportes/Resistencias) y su voto. Úsalo cuando el usuario diga "los indicadores", "RSI/MACD/EMA", "cómo vota cada indicador", "pesos de indicadores", o al tocar scoring_strategy / indicators / system_wiring.
---

# 03 · Indicadores (los 10 del sistema)

Los indicadores exactos del trader y cómo cada uno "vota" CALL/PUT/HOLD. Comentar el
PORQUÉ (la razón/matemática), no el qué.

## Los 10 (parámetros del trader — NO cambiar sin pedir)
EMA 8/20/50/200 · Estocástico 5,3,3 · Bollinger 14, 1.02 · Donchian 20 · RSI 5 ·
MACD 12,26,9 · Soportes/Resistencias. Definidos en `bot/otc_system.INDICADORES_OTC`.

## Archivos
- `bot/otc_system.py` / `bot/real_system.py` — config del trader (indicadores,
  pesos por tiempo, alineación mínima, ciclo de mercado, payout).
- `bot/system_wiring.py` — `votar_sistema(df, sistema)`: cada indicador vota con
  sus params exactos (`_ema_vote`, `_rsi_vote`, `_stochastic_vote`, `_macd_vote`,
  `_bollinger_vote`, `_donchian_vote`, `_soporte_resistencia_vote`).
- `bot/scoring_strategy.py` — 8 indicadores que votan con pesos por régimen; carga
  `core/indicators.py` (dependencia REAL, no borrar esa carpeta).

## Régimen (ajusta pesos)
ADX decide: en tendencia mandan MACD/medias; en rango mandan rebotes techo/piso
(RSI/Bollinger). `weights_for()`, `regime()`.

## Probar
```bash
python -m bot.test_system_wiring
python -m bot.test_scoring_strategy
```
