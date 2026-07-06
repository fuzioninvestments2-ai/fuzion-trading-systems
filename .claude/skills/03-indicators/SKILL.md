---
name: 03-indicators
description: Quantum Trading Core · Indicadores (RSI, MACD, Bollinger, Estocástico, momentum, volumen) con dirección (+1/-1) y fuerza (0-1) por cada uno de los 9 timeframes. Úsalo cuando el usuario diga "los indicadores", "RSI/MACD/EMA", "fuerza de indicadores", "cómo vota cada indicador".
---

# 03 · Indicadores (dirección + fuerza por timeframe)

Cada indicador da DIRECCIÓN (+1/-1) y FUERZA (0-1) según su distancia a la zona
neutral. Es la materia prima del motor cuántico (Skill 04).

## `calculate_indicators(df)` → `bot/cuantico.calculate_timeframe_signal(df)`
Combina, por timeframe, y devuelve `(direccion ±1, fuerza 0-1, porcentaje 0-100)`:
- **Momentum** = (cierre − apertura) / (máx − mín).
- **RSI**: dir por 50; fuerza = |RSI−50|/50.
- **Bollinger**: posición = (precio − media)/(sup − inf).
- **MACD**: dir por línea vs señal; fuerza = |macd − señal|/|macd|.
- **Estocástico**: dir por K vs D; fuerza = |K − D|/100.
- **Volumen relativo**: vol/promedio(20) → atenúa la fuerza si es bajo.

`porcentaje` = 50 neutral; >50 alcista; <50 bajista.

## Config del trader (paramétrica)
`bot/otc_system.py` (EMA 8/20/50/200, RSI 5, Estocástico 5,3,3, Bollinger, Donchian,
MACD 12,26,9, S/R), `bot/system_wiring.py` (voto por indicador), `bot/scoring_strategy.py`.

## Probar
```bash
python bot/test_cuantico.py
python bot/test_system_wiring.py
```
