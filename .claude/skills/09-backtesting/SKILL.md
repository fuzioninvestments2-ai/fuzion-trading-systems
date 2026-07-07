---
name: 09-backtesting
description: Quantum Trading Core · Simula el sistema sobre el HISTORIAL real (9 timeframes) y mide el win-rate REAL, sin mirar el futuro. Úsalo cuando el usuario diga "backtest", "simulación", "medir aciertos", "win-rate real", "cuántas se filtran", "la danza sobre el historial".
---

# 09 · Backtesting / Simulación histórica

Aplica el MISMO motor que corre en vivo a datos ya ocurridos y mide el win-rate
REAL. Honesto por diseño: el número que sale es el número; no se infla.

## Simulación sobre el historial real → `bot/backtest_historico.py`
Reconstruye los 9 timeframes (5,10,15,60,120,180,300,600,900s) desde
`datasets/*__tf5.csv.gz` por resampleo, camina hacia adelante y en cada punto corre
`validate_signal_90` con SOLO velas ya cerradas (anti look-ahead), midiendo el
resultado a 60s (entrada 1m).

```bash
python -m bot.backtest_historico        # 30 pares
python -c "from bot.backtest_historico import correr; correr(n_pares=95)"   # todos
```

### Resultado MEDIDO (95 pares OTC, 2.402 señales resueltas)
- **Win-rate real: 48%** (intervalo 95%: 46-50%).
- Break-even con payout 92%: **52.08%** → el sistema **pierde** a largo plazo en OTC.
- Estratificado: ni el subconjunto más fuerte gana. 9/9 alineados = 48.5%;
  probabilidad 95-100% = 47.9%. Las señales "más fuertes" no aciertan más — firma
  de ruido: en el feed OTC sintético la confianza NO está correlacionada con el
  resultado. Ser más selectivo no sube el acierto.

> Por qué importa: el OTC es sintético y sin memoria (autocorrelación ~0). Ningún
> conjunto de indicadores lo vuelve rentable. El backtest lo demuestra con TUS
> datos, no con una opinión. El bot sirve como DISCIPLINA (filtra ruido, frena en
> S/R y horas malas), no como generador de ganancia garantizada.

## Backtest del registro en vivo → `bot/cuantico.backtest_quantum_system(db, 100)`
Toma las últimas 100 señales RESUELTAS del `history.db`, aplica el gate de
convergencia ≥90% y reporta win-rate ANTES, cuántas FILTRA, cuántas PASAN y
win-rate ESTIMADO con sus motivos. Mide el acierto real acumulado del bot.

```bash
python bot/simular_reglas.py fuzion-otc/history.db 100
```

## Aprendizaje sobre historial
- `bot/backtester.py` (evalúa aciertos), `bot/calibration.py` (umbral por ~30 velas),
  `bot/weight_learning.py` (multiplicadores por indicador), `bot/signal_log.py`
  (registra cada señal con su probabilidad/convergencia en la columna `meta`).

## Probar
```bash
python bot/test_backtest_historico.py    # valida la mecánica (sin red, anti look-ahead)
python bot/test_backtester.py
```
