# Diagnóstico — Bot 5M mudo desde 7/8 + Bot 1M baja frecuencia (2026-08-11)

## Resumen ejecutivo

| Bot | Síntoma | Causa | Estado |
|-----|---------|-------|--------|
| **5M (f4_m5)** | Silencio total desde 7/8 | `min_confirmations: 4` con solo 4 indicadores votantes → **imposible estructural** | **FIX aplicado** (→ 3) |
| **1M (f1_m1)** | Hoy 1 señal en ~10h | Diseño anti-duplicado (emite solo al **cambiar** de dirección) + rareza de 3 confirmaciones → **dependiente del mercado**, no es un bug | Sin cambio (pendiente tu OK) |

> Aclaración de alcance: el diagnóstico es sobre el **código**. Los procesos corren en tu PC;
> la verificación de "proceso vivo" y logs en vivo la hacés vos (comandos al final).

---

## 5M — causa raíz (probada)

### El motor tiene SOLO 4 indicadores que votan
`core/signal_engine.py` (`_votos`): `ema`, `rsi`, `macd`, `bollinger`. Cada uno da +1 (CALL) / -1 (PUT) / 0.

Están partidos en dos familias que se **oponen** en los extremos:
- **Tendencia**: `ema` (rápida>lenta) y `macd` (histograma>0) → votan CALL cuando el precio **sube**.
- **Reversión**: `rsi` (<30 sobreventa) y `bollinger` (precio bajo banda inferior) → votan CALL cuando el precio **cae**.

Para juntar los **4** votos del mismo lado harían falta, a la vez, tendencia alcista **y**
sobreventa extrema: una contradicción. Por eso el 5M (`min_confirmations: 4`) **nunca**
llegaba al umbral y quedaba NEUTRAL en cada pasada → silencio total.

Los otros bots piden **3 de 4**, que sí ocurre en momentos de transición (un pullback corto
dentro de una tendencia), aunque es poco frecuente → por eso mandan pocas señales por día,
no un chorro.

### Evidencia (búsqueda de 200.000 escenarios sintéticos)
- Máximo de indicadores alineados hallado: **3. Nunca 4.**
- Caso real con 3 votos: `{ema:-1, rsi:-1, macd:+1, bollinger:-1}`
  - Con `min_confirmations=3` (nueva) → emite **PUT**.
  - Con `min_confirmations=4` (vieja) → **NEUTRAL** (mudo).

### Por qué "prueba de conexión ✅" sí llegó el 7/8
Ese mensaje es un envío manual de test (no pasa por la lógica de confirmaciones). Confirma que
el proceso y el token del 5M estaban bien; lo que fallaba era el umbral, no la conexión.

### Descartado
- **RiskManager**: `can_trade` en estado fresco devuelve True (sin pérdidas, sin recovery, sin
  trades). El 5M nunca emitió, así que nunca llegó a tocar el riesgo. No es el bloqueo.
- **SignalCardFormatter**: se creó el 10/8; el 5M está mudo desde el 7/8. No puede ser la causa
  (no existía). Descartado por línea de tiempo.
- **Datos insuficientes**: agravante posible las primeras ~3h tras arrancar (una vela de 5m
  necesita acumular ~35 velas para MACD/BB), pero tras 4 días la base ya tiene histórico. El
  bloqueo real y permanente es el umbral 4.

### FIX
`config/bots.yaml`, bot `f4_m5`: `min_confirmations: 4 → 3` (igual que 2M/3M). **Un solo campo,
de un solo bot.** No se tocó código ni config de 1M/2M/3M.

---

## 1M — análisis (sin cambio todavía)

El 1M tiene `min_confirmations: 3` (correcto). Ayer 7+ señales, hoy 1.

- El envío depende de dos cosas: (a) que se junten **3 confirmaciones** (momento raro de
  transición) y (b) el **anti-duplicado** `_last_dir`: solo avisa cuando la dirección **cambia**
  respecto al último aviso del par; si un par se mantiene CALL, no vuelve a avisar hasta que gire
  a PUT o pase por NEUTRAL.
- Resultado: la frecuencia es **sensible al mercado**. Un día con muchos giros de 3-alineados en
  los 22 pares → muchas señales; un día más tendencial/plano → pocas. Ayer volátil, hoy calmo.
- **La integración del formatter NO cambió la emisión**: solo tocó `build_card` /
  `_notificar_resultado` (formato). La lógica de `scan_once` (confirmaciones, anti-duplicado,
  rate-limit, pre-filtro) quedó intacta. No es una regresión.

### Opción a evaluar (NO aplicada — requiere tu OK)
Si querés más frecuencia en 1M sin romper el anti-spam: **re-armar** el anti-duplicado tras
vencer la señal (permitir re-avisar la misma dirección pasado 1 ciclo del timeframe), en vez de
exigir un cambio de dirección. Es un cambio de comportamiento de un bot que hoy funciona → lo
dejo para que decidas.

---

## Definición de "listo"
- [x] 5M: causa identificada y fix aplicado (emite como 2M/3M).
- [x] 2M/3M: sin tocar.
- [x] Suite completa 8/8 verde (sin red).
- [ ] **Verificación en vivo en tu PC** (ver comandos).
- [ ] 1M: decisión sobre re-armar anti-duplicado (pendiente tu OK).

## Verificación en tu PC (pasos)
1. Actualizá el código: doble clic en `INICIAR_FUZION_FX.bat` (hace `git pull` y arranca).
2. Confirmá que los 4 procesos están vivos: doble clic en `ESTADO_FUZION_FX.bat`.
3. Mirá el log del 5M: abrí `fuzion_fx/logs/f4_m5.log` — buscá líneas `Senal emitida`.
4. En 1-3 horas de mercado abierto el 5M debería empezar a mandar tarjetas al Telegram del 5M.
