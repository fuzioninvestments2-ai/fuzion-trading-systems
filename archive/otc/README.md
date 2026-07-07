# OTC — CERRADO (caso resuelto)

Este directorio archiva el análisis del proyecto **OTC** (Pocket Option, opciones
binarias sobre precio sintético). El proyecto se cierra con un veredicto claro,
sustentado en datos reales y en la prueba más dura (validación out-of-sample).

## Veredicto: **NO_OPERABLE**

El OTC de opciones binarias tiene **esperanza negativa** y ninguna estrategia
probada la vuelve positiva. No es opinión: es lo que dicen los datos.

## Evidencia (medida, no inventada)
- **101 activos, 517.270 velas M1** (2026-06-29 a 2026-07-04).
- Autocorrelación de retornos: **−0.0003** (0 = sin memoria = azar).
- Mejor predictor direccional medio: **50.58%** (necesario con payout 92%: 52.08%).
- Ventaja del broker: **−4% por operación** a win-rate 50%.
- **Validación out-of-sample** (12.045 señales, borde en 1ª mitad de pares
  verificado en 2ª mitad): NINGÚN nicho supera 54% en ambas mitades.

| Estrategia | In-Sample | Out-of-Sample |
|------------|-----------|---------------|
| Sistema cuántico (9 TF) | 50.4% | 49.5% |
| Momentum | 49.5% | 48.8% |
| Reversión | 50.5% | 51.2% |
| Reversión extrema | 49.0% | 52.5% |

## Por qué no se puede ganar
Pocket Option **genera** el precio OTC (sintético, sin memoria) y fija el payout
(92%) para que el equilibrio (52.08%) quede por encima de lo alcanzable en un
proceso ~50/50. La casa gana por diseño. Es una ruleta con gráfico.

## Qué SÍ aporta el bot en OTC
Herramienta de **disciplina y protección**: filtra ruido, frena en S/R y horas de
baja volatilidad, registra todo para auditar. Reduce operaciones malas. NO genera
ganancia esperada positiva.

## Reproducibilidad
```bash
python -m bot.backtest_historico          # win-rate real del sistema (~48%)
python archive/otc/analisis/reporte_otc.py    # datos del reporte
python archive/otc/analisis/buscar_borde.py   # validación out-of-sample
```

## Motor compartido
El motor cuántico (`bot/cuantico.py`) y los indicadores se **conservan**: el
proyecto FX (Mercado Real) los reutiliza. Archivar OTC no borra código compartido;
archiva el análisis y marca el proyecto OTC como cerrado.

Reporte completo: `archive/otc/REPORTE_OTC.md`.
