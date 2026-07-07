# REPORTE DE ANÁLISIS DE MERCADO OTC - OPCIONES BINARIAS

> **Nota de honestidad sobre las fuentes.** Los datasets disponibles (`datasets/*.csv.gz`)
> son **velas OHLC** (timestamp, open, high, low, close, volume). **NO contienen**
> stream de payout en el tiempo, ni bid/ask spread, ni tiempos de tick individuales.
> Por eso: el Análisis 1 es matemática exacta (universal); el Análisis 2 se hace con
> **proxies de la vela** (rango high-low, huecos de tiempo), no con spread real; el
> Análisis 3 (patrones de cambio de payout) **no tiene datos** y se marca como tal;
> el Análisis 4 se mide directamente sobre los precios. No se inventa ningún número.

## DATOS ANALIZADOS
- Total de activos analizados: **101** (con ≥100 velas M1; 105 archivos M1 en total)
- Total de velas M1 analizadas: **517.270**
- Periodo de análisis: **2026-06-29 08:11 UTC** a **2026-07-04 11:51 UTC**
- Timeframes por activo: 5s, 10s, 15s, 30s, 1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d
- Activos: 101 pares OTC (acciones #AAPL/#BA/#TSLA…, FX EURUSD/GBPJPY…, cripto BTC/ETH…, índices AUS200/VIX…, metales XAUUSD)

---

## ANÁLISIS 1: WIN RATE MÍNIMO NECESARIO

> El payout no está en los datasets (es un parámetro que fija el broker en vivo). La
> tabla siguiente es **matemática exacta** y aplica a **todos** los activos por igual.
> El win-rate de equilibrio sale de: `p · payout = (1−p) · 100 → p = 100/(100+payout)`.

### Parámetro real del trader: payout 92%

**Win Rates Calculados (payout 92%):**
- Win rate equilibrio: **52.08%**
- Win rate mínimo rentable (margen +2%): **54.08%**
- Con payout mínimo típico OTC (85%): equilibrio 54.05%
- Con payout alto (95%): equilibrio 51.28%

**Tabla de Payouts vs Win Rates Necesarios (universal, exacta):**
| Payout (%) | Win Rate Equilibrio (%) | Win Rate Mínimo Rentable (%) |
|------------|-------------------------|------------------------------|
| 75         | 57.14                   | 59.14                        |
| 80         | 55.56                   | 57.56                        |
| 85         | 54.05                   | 56.05                        |
| 86         | 53.76                   | 55.76                        |
| 87         | 53.48                   | 55.48                        |
| 88         | 53.19                   | 55.19                        |
| 89         | 52.91                   | 54.91                        |
| 90         | 52.63                   | 54.63                        |
| 91         | 52.36                   | 54.36                        |
| 92         | 52.08                   | 54.08                        |
| 93         | 51.81                   | 53.81                        |
| 94         | 51.55                   | 53.55                        |
| 95         | 51.28                   | 53.28                        |

**Conclusión:** Con el payout 92% que operas, necesitas acertar **52.08%** solo para
no perder, y **54.08%** para ganar con margen. El win-rate medido del sistema y de
todas las estrategias probadas es **~50%** (ver Análisis 4). La brecha de 2-4 puntos
es exactamente la ventaja de la casa, y no se cierra con indicadores.

---

## ANÁLISIS 2: DETECCIÓN DE MANIPULACIÓN DE SPREADS

> **Sin spread real en los datos.** Se usa el **rango de la vela** `(high−low)/open`
> en puntos básicos (bps) como proxy de dispersión, y los **huecos de tiempo** entre
> velas. La latencia de ticks y el bid/ask **no son medibles** con velas.

### Muestra representativa (M1)

**Rango de vela (proxy de dispersión), por activo:**
| Activo | Rango medio (bps) | Std (bps) | Velas anómalas (>3σ) | % anómalas | Huecos >90s | Gap máx |
|--------|-------------------|-----------|----------------------|-----------|-------------|---------|
| #AAPL_otc  | 5.2  | 1.9  | 77 | 1.49% | 0  | 60s     |
| EURUSD_otc | 3.1  | 5.2  | 1  | 0.02% | 17 | 23.220s |
| BTCUSD_otc | 0.1  | 0.0  | 75 | 1.45% | 0  | 60s     |
| AUS200_otc | 0.3  | 0.1  | 88 | 1.71% | 0  | 60s     |

**Detección de anomalías (global, 101 activos):**
- % medio de velas anómalas (rango >3σ): **0.87%** (bajo; consistente con proceso estable)
- Cadencia de vela: **60s fija** en casi todos (gap medio entre velas ≈ 60s)
- Activos con huecos de tiempo: **21 de 101** — casi todos en FX, coinciden con cierre
  de sesión/fin de semana (ej. EURUSD gap de ~6.5h = frontera de sesión, no manipulación)

**Análisis de Latencia:** **[SIN DATOS]** — las velas tienen cadencia fija de 60s;
no hay ticks individuales para medir latencia.

**Diagnóstico de Manipulación:**
- Criterio 1 (Spread promedio >5 pips): **[SIN DATOS de spread real]**
- Criterio 2 (>5% ticks anómalos): **NO** (0.87% medio con proxy de rango)
- Criterio 3 (>10 huecos/hora): **NO** (huecos solo en fronteras de sesión FX)
- Criterio 4 (Latencia artificial frecuente): **[SIN DATOS]**

**Veredicto Final:** **NORMAL** en lo medible. Aclaración: que no haya *anomalías de
spread* NO significa mercado justo. Lo llamativo del OTC no es la manipulación tick a
tick, sino su **naturaleza sintética** (ver Análisis 3-4): precio generado, sin memoria.

**Conclusión:** Con velas OHLC no se puede probar manipulación de spread ni latencia.
Lo que sí es visible —cadencia perfecta de 60s, dispersión estable, ~50/50 de subidas—
es coherente con un **generador sintético controlado**, no con un mercado con oferta y
demanda reales.

---

## ANÁLISIS 3: PATRONES EN CAMBIOS DE PAYOUT

> **[SIN DATOS]** — Los datasets no incluyen ningún registro de payout en el tiempo,
> ni de volumen call/put, ni de payout_call vs payout_put. **Ninguna** métrica de esta
> sección es calculable con la información disponible. No se inventan valores.

**Estadísticas de Cambios:** [SIN DATOS de payout]
**Análisis de Correlaciones (payout vs volatilidad/volumen/spread):** [SIN DATOS de payout]
**Análisis de Periodicidad:** [SIN DATOS de payout]

**Conclusión:** Para llenar esta sección haría falta capturar el stream de payout en
vivo (websocket de Pocket Option), guardándolo junto a la volatilidad instantánea.
Es un dato que hoy el bot **no** registra. Sin capturarlo, cualquier número aquí sería
inventado — y eso está prohibido por las reglas del proyecto.

---

## ANÁLISIS 4: VENTAJA ESTADÍSTICA EXPLOTABLE

> Esta es la sección que **sí** se mide directamente sobre los precios, y es la que
> importa. Incluye la validación out-of-sample (borde en 1ª mitad de pares, verificado
> en 2ª mitad).

**Ventaja del Broker (matemática, payout 92%):**
- A win-rate 50% (lo medido): esperanza = **−4.00% por operación** (esta es la ventaja de la casa)
- La ventaja del broker es estructural: existe en cada operación mientras aciertes ≤52.08%

**Predictibilidad direccional (medida sobre 101 activos, 517.270 velas):**
- Autocorrelación media de retornos: **−0.0003** (0 = sin memoria = azar)
- % medio de velas alcistas: **49.56%** (≈ 50/50)
- Mejor predictor direccional medio (momentum/reversión): **50.58%**
- Activo más "predecible" en-muestra: LTCUSD_otc **52.08%** — y NO sobrevive fuera de muestra

**Cálculo de Rentabilidad Potencial (esperanza por operación, payout 92%):**
- Si win rate = 50%: **−4.00%** (realidad medida)
- Si win rate = 52.08%: **−0.01%** (equilibrio)
- Si win rate = 55%: **+5.60%**
- Si win rate = 60%: **+15.20%**
- Si win rate = 65%: **+24.80%**
- **Win rate mínimo para esperanza positiva: 52.09%** (inalcanzable con lo medido)

**Validación OUT-OF-SAMPLE (la prueba dura — 12.045 señales):**
| Estrategia | In-Sample (1ª mitad de pares) | Out-of-Sample (2ª mitad) |
|------------|-------------------------------|--------------------------|
| Sistema cuántico (9 TF) | 50.4% | 49.5% |
| Momentum (seguir vela)  | 49.5% | 48.8% |
| Reversión (contra vela) | 50.5% | 51.2% |
| Reversión extrema (3 velas) | 49.0% | 52.5% |
| **Nichos por hora/par que aguanten >54% en ambas mitades** | **NINGUNO** | |

**Oportunidades Detectadas:** **NINGUNA que sobreviva fuera de muestra.** Cualquier
activo que en la 1ª mitad parece pasar del 52% cae a ~50% en la 2ª. Es la firma del azar.

**Conclusión:** No existe ventaja estadística explotable. El mejor predictor (~50.6%)
está por debajo del 52.08% de equilibrio, y ningún nicho persiste out-of-sample. La
ventaja del broker (−4%/op a 50%) se mantiene intacta.

---

## RESUMEN EJECUTIVO COMPARATIVO

### Tabla Comparativa (15 activos con más datos)
| Activo | Payout Prom | Win Rate Mín | Rango Prom (proxy) | Manipulación | Ventaja Broker | Explotable |
|--------|-------------|--------------|--------------------|--------------|----------------|------------|
| EURUSD_otc | 92.00% | 52.08% | 3.1 bps  | NORMAL | 4.00% | NO |
| VIX_otc    | 92.00% | 52.08% | 4.8 bps  | NORMAL | 4.00% | NO |
| EURJPY_otc | 92.00% | 52.08% | 3.3 bps  | NORMAL | 4.00% | NO |
| #BA_otc    | 92.00% | 52.08% | 8.6 bps  | NORMAL | 4.00% | NO |
| EURCHF_otc | 92.00% | 52.08% | 10.2 bps | NORMAL | 4.00% | NO |
| USDINR_otc | 92.00% | 52.08% | 1.9 bps  | NORMAL | 4.00% | NO |
| GBPJPY_otc | 92.00% | 52.08% | 8.4 bps  | NORMAL | 4.00% | NO |
| XAUUSD_otc | 92.00% | 52.08% | 0.1 bps  | NORMAL | 4.00% | NO |
| USDMXN_otc | 92.00% | 52.08% | 8.7 bps  | NORMAL | 4.00% | NO |
| CHFJPY_otc | 92.00% | 52.08% | 5.8 bps  | NORMAL | 4.00% | NO |
| #AAPL_otc  | 92.00% | 52.08% | 5.2 bps  | NORMAL | 4.00% | NO |
| BTCUSD_otc | 92.00% | 52.08% | 0.1 bps  | NORMAL | 4.00% | NO |
| AUS200_otc | 92.00% | 52.08% | 0.3 bps  | NORMAL | 4.00% | NO |
| USDRUB_otc | 92.00% | 52.08% | 0.4 bps  | NORMAL | 4.00% | NO |
| GBPUSD_otc | 92.00% | 52.08% | 4.5 bps  | NORMAL | 4.00% | NO |

*(Los 101 activos dan el mismo veredicto: Explotable = NO. Payout y ventaja del broker
son iguales para todos porque el payout lo fija el broker, no el activo.)*

### Ranking de Activos (Mejor a Peor para Trading)
No hay ranking operativo real: **los 101 son estadísticamente equivalentes a una moneda
al aire**. Cualquier orden entre ellos (por rango, por "mejor predictor" en-muestra) es
ruido que no persiste. Ordenar activos aquí daría una falsa sensación de que uno es mejor.

---

## CONCLUSIONES FINALES

### 1. Sobre Win Rate Necesario
Con payout 92% necesitas **52.08%** para no perder y **54.08%** para ganar con margen.
La tabla es exacta y universal. El problema no es el número necesario —es modesto—,
sino que el mercado OTC no entrega ni siquiera el 52%: se mide **~50%** en todo.

### 2. Sobre Manipulación del Mercado
Con velas OHLC no se puede detectar manipulación de spread ni de latencia (no hay tick
ni bid/ask en los datos). Lo medible es NORMAL. Pero lo relevante no es manipulación
puntual: es que el precio OTC es **sintético**, con cadencia perfecta de 60s, dispersión
estable y sin memoria — un proceso generado, no un mercado.

### 3. Sobre Patrones del Broker
No hay datos de payout para analizarlo. Lo que la teoría del negocio dice y los precios
confirman: el broker fija el payout (92%) de modo que el equilibrio (52.08%) quede por
encima de lo que un jugador puede lograr en un proceso ~50/50. Así la casa gana por diseño.

### 4. Sobre Ventaja Explotable
**No existe.** Autocorrelación ~0, mejor predictor 50.6%, ningún nicho sobrevive
out-of-sample. La ventaja del broker (−4% por operación a 50%) permanece intacta en los
101 activos.

### 5. Recomendación Final
**VEREDICTO: NO_OPERABLE**

**Justificación:** Los cuatro análisis apuntan a lo mismo. (1) El win-rate necesario
(52.08%) es alcanzable en teoría pero (4) el mercado entrega ~50%, medido sobre 517.270
velas y validado fuera de muestra. (2) No hay señal de manipulación *ni de estructura
explotable* en las velas; el precio es sintético. (3) El broker controla el payout para
mantener su ventaja. La conclusión es matemática, no de opinión: **operar OTC de opciones
binarias tiene esperanza negativa (−4%/operación) y ninguna estrategia de las probadas la
vuelve positiva.**

**Condiciones para Operar:** No hay condiciones bajo las cuales OTC sea rentable de forma
sostenida con estos datos. El bot debe usarse como **filtro de disciplina y protección**
(reducir operaciones malas), entendiendo que no genera ganancia esperada positiva.

**Win Rate Mínimo Requerido para Ser Rentable:** 52.09% (payout 92%). **Medido: ~50%.**

**Rentabilidad Esperada Mensual (realidad, win-rate 50%, payout 92%, −4%/op):**
- Con 100 operaciones/mes: **−4% por operación acumulado** (pérdida esperada, ~ −33% del capital arriesgado con reinversión)
- Con 500 operaciones/mes: pérdida esperada mayor por más exposición
- Con 1000 operaciones/mes: cuantas más operaciones, **más rápido se materializa la pérdida** (ley de grandes números a favor de la casa)

> La única cifra "mensual" honesta: a más volumen operado en OTC, más seguro es perder.
> El camino con esperanza potencialmente positiva es el **Mercado Real (FX)**, donde el
> precio no lo genera el broker — se analiza en su propio proyecto y con el mismo rigor.

---

## ANEXOS TÉCNICOS

### A. Fórmulas Utilizadas

**Win Rate de Equilibrio:**
```
p · payout% = (1 − p) · 100
p = 100 / (100 + payout%)
Ej. payout 92 → p = 100/192 = 52.08%
```

**Esperanza por operación (EV):**
```
EV% = [ p · (payout%/100) − (1 − p) ] · 100
Ej. p=0.50, payout 92 → (0.50·0.92 − 0.50)·100 = −4.00%
```

**Rango de vela (proxy de dispersión, en bps):**
```
rango_bps = (high − low) / open · 10.000
```

**Autocorrelación (memoria del precio):**
```
r = corr(retorno_t, retorno_{t−1});  retorno = (close − open)/open
r ≈ 0  →  sin memoria  →  no predecible
```

**Validación out-of-sample:** borde medido en 1ª mitad de pares (IS) y verificado en
2ª mitad (OOS); solo es real si win-rate > 54% en ambas con n ≥ 100.

### B. Reproducibilidad
```bash
python -m bot.backtest_historico              # win-rate real del sistema
python -m scratchpad.reporte_otc              # datos de este reporte
python -m scratchpad.buscar_borde             # validación out-of-sample
```
