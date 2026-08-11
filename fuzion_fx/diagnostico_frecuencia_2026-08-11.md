# Diagnóstico — Baja frecuencia de señales (todas las temporalidades) — 2026-08-11

## Síntoma
M1 mandó solo ~2 señales desde ayer (mercado abierto). Se esperaría ~1 cada
10 min por timeframe. Afecta a los 4 bots (mismo motor).

## Causa raíz (cuantificada)
El motor vota con 4 indicadores, pero **2 casi nunca votan**:

| Indicador | % de velas en que vota (no-cero) | Condición |
|-----------|----------------------------------|-----------|
| ema | 100% | rápida vs lenta (siempre hay lado) |
| macd | 100% | histograma >0 / <0 (siempre hay lado) |
| **rsi** | **9.1%** | solo si <30 o >70 (extremo) |
| **bollinger** | **11.3%** | solo si el precio sale de las bandas (extremo) |

Como RSI y Bollinger están en 0 el ~90% del tiempo, en la práctica hay **2
votantes activos** (ema, macd). Distribución del máximo alineado (20.000 velas FX
sintéticas realistas):

- 2 alineados: **68.2%**  (ema+macd)
- 3 alineados: **0.1%**
- 4 alineados: **0.0%**

Con `min_confirmations: 3`, el motor emite en **0.05%** de las lecturas. Con 22
pares eso da unas pocas señales por día → coincide con lo observado.

### Factor secundario: datos ralos del colector
El colector rota 22 pares × 8s ≈ 176s por vuelta: cada par recibe ticks ~8s cada
~3 min. Para velas de 1 min, muchos pares quedan "fríos" (sin ticks) en varios
minutos → velas planas → menos señales aún. Es best-effort por el límite de 1
conexión de Pocket Option.

## Lo que NO es
- No es que el bot esté caído (ESTADO = 6 CORRIENDO).
- No se pierde aprendizaje al apagar/encender: el win/loss por setup está en las
  sqlite (`f*_memory.db`); `LearningEngine` lee de la DB en cada evaluación.

## Opciones para subir la frecuencia (requieren tu OK; hay trade-off)
El sistema hoy es de **alta precisión / baja cantidad**: pocas señales pero cada
una respaldada por tendencia + un extremo. Para tener más señales hay que aflojar,
y más cantidad NO implica más aciertos. Caminos:

1. **Recalibrar RSI y Bollinger** para que aporten voto direccional más seguido
   (bandas 45/55 en RSI, sensibilidad de Bollinger), en vez de solo en extremos.
   Es el arreglo más limpio; se **calibra con el backtester** sobre el historial
   real para apuntar a ~1 señal/10 min sin destrozar el win-rate.
2. **Agregar 1-2 indicadores** independientes (estocástico, pendiente de EMA,
   precio vs VWAP) para que 3-de-N sea alcanzable con más frecuencia.
3. **Mejorar la cobertura del colector** (menos segundos por par o priorizar
   pares activos) para velas menos ralas.

Recomendado: (1) + calibración por backtest, y si hace falta (2). Todo tuneado
contra los datos reales ya recolectados, no a ojo.

## Honestidad
Subir la frecuencia afloja los filtros. Se mide el win-rate en backtest antes de
dejarlo fijo. No se promete más aciertos; se busca el punto donde haya señales
útiles sin caer en ruido.
