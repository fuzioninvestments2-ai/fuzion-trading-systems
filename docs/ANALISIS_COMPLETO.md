# Análisis completo — OTC y FX (Mercado Real)

Resumen honesto de todo lo investigado, con los datos que lo sustentan. Regla del
proyecto: que decida el dato, no la opinión; nunca prometer aciertos.

## 1. OTC (Pocket Option binarias sintéticas) — CERRADO

- Precio **sintético** generado por PO. Autocorrelación ~0 (sin memoria).
- 101 activos, 517.270 velas. Mejor predictor 50.6%. Ventaja de la casa −4%/op.
- Validación out-of-sample: **ningún** nicho supera el break-even (52.08% con payout 92%).
- **Veredicto: NO_OPERABLE.** Archivado en `archive/otc/`.

## 2. FX (Mercado Real) — infraestructura construida

Pipeline completo, probado (72 tests sin red):
- Descarga automática 22 pares (Yahoo) → `historical_loader` + `dataset_export`.
- Sub-minuto real (5s-30s) desde Dukascopy → `dukascopy_loader`.
- Derivados 2m/3m/10m/4h desde 1m → `resamplear`.
- Estudio por timeframe (autocorrelación, predictor, motor, OOS) → `estudio_fx`.
- Ensemble de skills que aprende de resultados reales → `bot/skills/`.
- Estudios de condiciones y verificaciones → `estudio_condiciones`, `verificar_*`.

## 3. FX — qué encontramos, con datos

### a) El FX real SÍ tiene memoria (a diferencia del OTC)
Autocorrelación de 1m negativa y consistente en los 20 pares: −0.13 a −0.22.
Es reversión de corto plazo real. **Pero es débil.**

### b) El sistema/ensemble NO gana (out-of-sample)
Ensemble con reversión + momentum, 20 pares, 1m/2m/3m: **winOOS 44-50%**. Ningún
par supera 52.08%. El aprendizaje degradó los pesos solo (detectó que no aciertan).

### c) Los segundos (5s-30s) son casi azar
Autocorrelación −0.02 a −0.05; predictor ~50-51%. El terreno NO está en los segundos.

### d) El "borde" del 61-69% era un ESPEJISMO (lección clave)
Un backtest de "reversión tras pico" dio 61-69% OOS con +33% por operación. Demasiado
bueno. Causa: la señal usa el **mismo precio** para medir el pico y para entrar
(`close[i+1]`); su ruido crea una reversión mecánica que crece con el tamaño del pico.

**Prueba decisiva (`verificar_skip`, 119.770 señales reales):**

| pico | INMEDIATA (comparte precio) | SALTADA (entrada fresca) |
|------|-----------------------------|--------------------------|
| 1-2 pips | 57.9% | 50.0% |
| 2-3 pips | 59.2% | 51.0% |
| 3-5 pips | 63.3% | 48.4% |
| ≥2 pips | **61.4%** | **50.0%** |

Con entrada FRESCA (lo único operable) el borde cae a 50.0% exacto. **No es operable.**
El 61-69% era el ruido corrigiéndose, imposible de capturar: para cuando ves el pico,
el precio ya volvió. Este es el error que arruina a la mayoría de los bots caseros;
aquí se cazó ANTES de arriesgar dinero.

## 4. Veredicto honesto

Con análisis técnico (indicadores, reversión, momentum, ensemble que aprende) sobre
datos reales de 20 pares y 13 temporalidades, **no se encontró un borde operable para
opciones binarias de FX**. La única señal que superó el filtro resultó ser un artefacto,
probado con datos. El FX real tiene memoria, pero es demasiado débil para vencer el
52.08% que exige el payout 92% — y desaparece al entrar con precio real.

Esto coincide con la teoría: a estas escalas los mercados son casi eficientes y las
binarias son de suma negativa (el broker fija el payout a su favor).

## 5. Qué SÍ se logró

- Un sistema de investigación **riguroso y honesto**, todo con tests y reproducible.
- Se respondió la pregunta con TUS datos, no con opiniones.
- Se evitó una pérdida real: el "65%" habría costado dinero; se descartó con pruebas.
- El bot sirve como herramienta de **disciplina/protección** (filtra ruido), no de ganancia.

## 6. Caminos honestos hacia adelante (sin promesas)

1. **Aceptar** que las binarias (OTC y FX) no se vencen con esto y usar el bot solo
   como disciplina, o parar de arriesgar en binarias.
2. **FX spot** (comprar/vender la divisa, no binarias): el listón no es 52% sino el
   spread. Un edge pequeño podría ser rentable con gestión de riesgo — pero es OTRO
   instrumento, otro broker, y NO está probado que exista. Sería empezar otra
   investigación, con el mismo rigor y sin garantías.
3. **Forward-test en demo**: ya no aplica a la señal del pico (fue refutada). Solo
   tendría sentido si aparece un candidato que sobreviva la prueba de entrada fresca.

## Reproducibilidad
```bash
python -m bot.estudio_fx --pairs all --timeframes 1m,2m,3m,5m,15m,30m,1h
python -m bot.skills.backtest_ensemble --pairs all --timeframes 1m,2m,3m
python -m bot.verificar_skip        # la prueba que refutó el "borde"
```
