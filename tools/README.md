# Optimizador de crecimiento

Herramienta para encontrar los parámetros que dan **mejor expectativa y menor
drawdown** (no mejor win rate) sobre el universo multi-activo.

## Qué optimiza

`tools/strategy_core.py` es una versión Python (sobre velas cerradas) del motor
del QUANT BOT v5: tendencia + momentum con los mismos filtros de calidad
(confianza mínima, breakeven, timeout, drawdown diario, bloqueo por objetivo) y
**costes realistas**. No replica el Pine tick a tick; sirve para medir y comparar
configuraciones de forma honesta.

`growth_score = expectativa_R × √(nº trades) / (1 + drawdown × 5)`

- Premia **expectativa** (ganar más por trade que lo que se arriesga).
- Premia tener **muestra suficiente** (no se fía de 5 operaciones afortunadas).
- Castiga el **drawdown**.
- **No premia el win rate.** Un 40% de aciertos con buen R:R gana a un 80% que
  pierde fuerte cuando falla.

## Uso (CLI)

```bash
pip install -r requirements.txt

# Optimiza todas las cripto (diario, 5 años)
python scripts/run_optimizer.py --class crypto

# Símbolos concretos
python scripts/run_optimizer.py --symbols NVDA TSLA AAPL --period 5y

# Todo el universo intradía 5m (yfinance limita ~60 días en 5m)
python scripts/run_optimizer.py --class all --interval 5m --period 60d

# Más combinaciones
python scripts/run_optimizer.py --class forex --samples 200
```

Imprime un ranking y guarda el detalle en `results/optimizer_*.json`
(incluye métricas por símbolo).

## Uso (código)

```python
from tools.optimizer import Optimizer
opt = Optimizer()
report = opt.run(symbols=["NVDA", "BTC-USD"], interval="1d",
                 period="5y", n_samples=120)
print(report["best"]["params"])
opt.save(report)
```

## Cómo llevar el resultado al bot de TradingView

El optimizer te da, p. ej., `atr_sl_mult=2.0`, `rr=2.5`, `min_confidence=70`,
`adx_min=25`. Lleva esos valores a los inputs equivalentes del Pine:
`M2 SL = xATR`, `M2 TP1 (xR)`, `Confianza mínima`, y el umbral ADX. Re-testea en
TradingView con **Backtest honesto = ON** antes de operar.

> Aviso honesto: optimizar siempre corre riesgo de sobreajuste. Usa periodos
> largos, valida en datos que el optimizer NO vio, y desconfía de scores que solo
> suben por subir el riesgo por operación.
