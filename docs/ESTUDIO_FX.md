# Estudio FX (Mercado Real) — arranque honesto

Proyecto activo tras cerrar OTC. Misma metodología, mismo rigor, misma honestidad:
se mide, no se inventa; un borde solo cuenta si sobrevive **out-of-sample**.

## Diferencia de fondo con OTC
- **OTC**: precio sintético que genera Pocket Option. Autocorrelación ~0, sin
  memoria. Veredicto probado: NO_OPERABLE (ver `archive/otc/`).
- **FX real**: precio de mercado con bancos, oferta y demanda. PUEDE tener memoria.
  Es la razón de mover el esfuerzo aquí.

## Qué datos hay HOY (real, no OTC)
| Activo | Timeframes con datos | Nota |
|--------|----------------------|------|
| EURCAD | 1m, 3m, 5m, 15m, 30m | único con historia útil (hasta 1.400h en 30m) |
| CHFJPY | 1m (~60 velas) | insuficiente |
| USDCAD | 1m (~60 velas) | insuficiente |

Faltan: casi todos los pares y los tiempos 5s-4h. **No se pueden bajar desde este
contenedor** (la red cloud bloquea Yahoo/TradingView/PO con 403). Se consiguen en la
PC del trader (export de TradingView o `historical_loader` con yfinance) y se suben.

## Hallazgo inicial (EURCAD) — medido con `bot/estudio_fx.py`
| TF | velas | autocorrelación | %up | mejor predictor (IS) | motor OOS (IS→OOS) |
|----|-------|-----------------|-----|----------------------|--------------------|
| 1m  | 3243 | −0.108 | 45.9% | 51.8% | 47.5% → 48.2% |
| 3m  | 2999 | −0.049 | 34.9% | 63.5% | 48.4% → 47.2% |
| 5m  | 2948 | −0.101 | 39.6% | 58.3% | 60.2% → 46.4% |
| 15m | 2949 | −0.076 | 37.9% | 61.3% | 49.3% → 37.6% |
| 30m | 2800 | −0.046 | 37.8% | 63.3% | 57.1% → 47.5% |

**Lectura disciplinada (sin hype):**
1. **La autocorrelación es negativa y consistente (−0.05 a −0.11)**, no ~0 como el
   OTC. Es memoria real: tendencia a la reversión de corto plazo. Esto es lo que
   diferencia al FX y justifica seguir.
2. **Pero el motor NO gana out-of-sample**: los números altos en-muestra (60%) se
   caen a ~46-48% en la 2ª mitad. Es sobreajuste, la misma lección del OTC.
3. **El %up bajo (35-46%)** indica que este período de EURCAD tuvo sesgo direccional
   (tendencia), lo que infla los predictores en-muestra. Un solo par y un solo
   régimen no bastan para concluir.

**Conclusión de arranque:** el FX real tiene estructura estadística que el OTC no
tenía, pero con un solo par no hay borde probado. El cuello de botella es DATOS: más
pares, más historia, más regímenes. No se fuerza una conclusión que el dato no da.

## Plan (cuando lleguen los datos)
1. Subir `datasets/*.csv.gz` de los 22 pares forex, tiempos 5s-4h (lo que TradingView
   exporte; sub-minuto puede no existir para FX — se marca "sin datos" si falta).
2. `python -m bot.estudio_fx` sobre todos → tabla autocorrelación/OOS por par y TF.
3. Diseñar la estrategia SOBRE lo que el estudio muestre (probablemente reversión de
   corto plazo por la autocorrelación negativa), no al revés.
4. Validar out-of-sample TEMPORAL (el 30m de EURCAD ya abarca 1.400h: alcanza para
   partir en el tiempo, a diferencia del OTC).
5. Contrastar contra el costo real (spread): en FX el break-even es el spread, no un
   payout del 92%. Aquí un borde pequeño SÍ puede ser rentable si supera el spread.

## Reproducibilidad
```bash
python -m bot.estudio_fx          # estudio por timeframe + OOS
python bot/test_estudio_fx.py     # test de la mecánica (sin red)
```
