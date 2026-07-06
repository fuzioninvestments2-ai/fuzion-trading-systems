---
name: 13-multi-timeframe
description: La SINFONÍA DE DIRECCIÓN del trader — lectura de los 12 tiempos (5s→1H) con su regla por temporalidad, pesos y alineación 7/12. Úsalo cuando el usuario diga "sinfonía", "alineación multi-timeframe", "la lectura por tiempo", "5s/10s/.../1H", "qué indica cada tiempo", o al tocar alignment / deep_analysis / otc_system.
---

# 13 · Multi-timeframe (sinfonía de dirección)

El corazón del sistema: leer TODOS los tiempos a la vez y operar solo cuando la
mayoría se alinea con la dirección absoluta (EMA200 de 1H). El trader mira 5s→1D en
6 pantallas; el bot lo replica leyendo las 12 temporalidades.

## Los 12 tiempos y su PESO (suman 100)
`1H=30 · 30m=20 · 15m=15 · 5m=10 · 2m=10 · 1m=5 · 30s=5 · 15s=3 · 10s=2` (`otc_system.PESOS_ALINEACION`).
Mínimo **7/12** alineados con 1H para OPERAR (`ALINEACION_MINIMA`).

## Regla por temporalidad (`bot/alignment.direccion_timeframe`)
- **1H** → EMA200 = **dirección ABSOLUTA**. Nunca operar contra ella.
- **30m / 5m** → EMA50 y EMA200 alineadas.
- **15m** → EMA50 alineada con 1H.
- **2m** → EMA20 > EMA50 > EMA200 (pila).
- **1m** → precio sobre/bajo EMA20.
- **30s** → MACD confirma.
- **15s** → Stochastic en zona favorable.
- **10s** → RSI 5 no en extremo contrario.
- **5s** → ruptura de Bollinger / entrada fina.

## Ciclo del mercado (formula)
Compresión → Acumulación → Saturación → Reversión (`otc_system.CICLO_MERCADO`).
Bollinger/Donchian estrechos = compresión; ruptura = inicio de movimiento.

## Lectura por tiempo (resumen del trader)
Los micro-tiempos (5s-30s) dan la ENTRADA fina; los medios (1m-5m) la dirección;
los macro (15m-1H) el SESGO/tendencia mayor. La entrada perfecta = mayoría alineada
con 1H + payout≥75 + sin noticias + sesión activa.

## SISTEMA PONDERADO 5s-15m (`bot/cuantico.py`)
Análisis de 9 timeframes con pesos por grupo y fórmulas del trader:
- **Ultra-cortos** (5s,10s,15s) = 15% · **Cortos** (1m,2m,3m,5m) = 50% ·
  **Medios** (10m,15m) = 35%.
- `calculate_timeframe_signal(df)` → (dir ±1, fuerza 0-1, %). Combina momentum,
  RSI, Bollinger, MACD, Estocástico (+volumen).
- `calculate_quantum_probability(frames)` → probabilidad = |Σ(w·s·f)/Σw|·C·100
  (C = correlación por nº alineados: 9→1.0, 8→0.89, 7→0.78, <7→0.67).
- `calculate_logarithmic_convergence(alineados)` → ln(1+alineados)/ln(1+9)·100
  (7/9=90.3%, 8/9=95.4%, 9/9=100%).
- `validate_signal_90(frames, datos, payout, hora_utc)` → OPERAR solo si
  convergencia≥90 Y probabilidad≥umbral Y filtros. Panel: `display_timeframe_panel`.
- Backtest: `backtest_quantum_system(db, 100)`.
- ⚠️ La probabilidad LITERAL rinde ~40% en tendencia fuerte (MACD/Stoch aportan
  poca fuerza): el gate operativo real es la CONVERGENCIA (7/9). Umbrales
  calibrables arriba de `cuantico.py`.

## GESTIÓN ESTRICTA DE TIMEFRAMES (`validate_signal`)
- **Prohibido operar si faltan tiempos por datos**: los 12 configurados deben tener
  velas. Si falta alguno → NO OPERAR (no se decide a ciegas).
- **Confirmación mínima por grupo** (fuerza = indicadores que confirman ese tiempo):
  - Cortos (1m-5m) ≥ **60%**.
  - Medios (10m-30m) ≥ **60%**.
  - Largos (1h+) ≥ **70%**.
  Si un tiempo no llega a su mínimo → NO OPERAR (ese tiempo no confirma).
- La **entrada la manda el tiempo operado** y sus vecinos (peso por proximidad en
  `bot/formula.py`); los tiempos lejanos son contexto.

## Archivos
`bot/alignment.py` (regla por tf + `evaluar_alineacion`), `bot/lectura_tiempo.py`
(lectura por tiempo + movimiento), `bot/formula.py` (fórmula de entrada),
`bot/validacion_senal.py` (reglas estrictas), `bot/otc_system.py` (pesos/tiempos/ciclo).

## Probar
```bash
python -m bot.test_alignment
```
