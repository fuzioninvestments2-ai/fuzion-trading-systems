---
name: 13-multi-timeframe
description: Quantum Trading Core · Los 9 timeframes (5s a 15m) — pesos por grupo (15/50/35%), validación de datos frescos y sincronizados antes del análisis. Úsalo cuando el usuario diga "los tiempos", "faltan tiempos", "9 timeframes", "sincronizar", "5s/10s/.../15m".
---

# 13 · Multi-timeframe (9 tiempos, 5s-15m)

Los 9 tiempos del Motor Cuántico y su salud. Sin datos completos y frescos, NO se
analiza.

## Los 9 tiempos y su PESO por grupo
- **Ultra-cortos** (5s, 10s, 15s) = **15%** (alta volatilidad, menos fiable).
- **Cortos** (1m, 2m, 3m, 5m) = **50%** (señal principal de Pocket Option).
- **Medios** (10m, 15m) = **35%** (tendencia base).
Peso individual = peso_grupo / nº del grupo (`bot/cuantico.GRUPOS`, `TIMEFRAMES_9`).

## `check_timeframe_health()` — datos frescos y sincronizados
- Cada uno de los 9 debe tener ≥20 velas FRESCAS (sesión actual en OTC). Si falta o
  está viejo, `validate_signal_90` devuelve "faltan N tiempos por datos" → NO OPERAR.
- Frescura/sincronía: `_frames_para_sistema` + `_recortar_sesion_otc` (Skill 02).

## Lectura por tiempo
Los ultra-cortos (5s-15s) dan la ENTRADA fina; los cortos (1m-5m) la señal principal;
los medios (10m-15m) la tendencia base. Cada uno da dir + fuerza + %
(`calculate_timeframe_signal`, Skill 03) → el Motor (Skill 04) los pondera.

## Config del trader (paramétrica)
`bot/otc_system.py` (indicadores, ciclo Compresión→Acumulación→Saturación→Reversión),
`bot/lectura_tiempo.py`, `bot/formula.py`.

## Probar
```bash
python bot/test_cuantico.py
python bot/test_panel_sistema.py
```
