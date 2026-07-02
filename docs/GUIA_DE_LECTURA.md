# Guía de lectura — cómo interpretar la señal en Telegram

Esta guía explica, en lenguaje sencillo, **cada línea** que el bot te muestra
cuando pulsas "Iniciar análisis". El objetivo es que entiendas *por qué* dice lo
que dice, no que lo obedezcas a ciegas.

> ⚠️ **Honestidad primero:** ningún bot acierta siempre, ni conoce la fórmula
> secreta de Pocket Option. Lo que hace este bot es **disciplina**: operar solo
> cuando varias cosas coinciden, y callar (avisar NO OPERAR) cuando el mercado
> está confuso, plano, vacío o manipulado. Todo es en **demo**, sin órdenes reales.

---

## Ejemplo de mensaje

```
📈 EUR/USD OTC   ⏱️ 1m   (REALES ✅)

✅ OPERAR
Dirección: ⬆️ UP (CALL)
📐 Modo: 📈 Slide (tendencia) → prioriza MACD/medias (ADX 27.3)
🎯 Alineación: 80%  (4/5 tiempos)
🧭 Lectura: RSI en sobreventa; MACD con impulso alcista; ...
🕯️ Patrones: Envolvente alcista (reversión ↑)
📏 VWAP: precio por ENCIMA (sesgo alcista) (+0.12%)

🔎 Panel de tiempos:
  15s 🟢 UP  ·  1m 🟢 UP  ·  5m 🟡 UP  ·  ...
⏱️ Entra al abrir la próxima vela (faltan 12s)
💵 Pago: 92%
```

---

## Línea por línea

### 🎯 Veredicto (lo primero que debes mirar)
- **✅ OPERAR** — alta coincidencia (≥75% de los tiempos y ≥3 tiempos de acuerdo).
- **🟡 OPCIONAL** — hay sesgo (≥60%) pero no es fuerte; entra solo si te sobra
  criterio propio.
- **🚫 NO OPERAR** — no hay claridad, o saltó una alerta de protección.

### Dirección
- **⬆️ UP (CALL)** = el bot ve más probable que suba.
- **⬇️ DOWN (PUT)** = más probable que baje.
- **😴 mercado plano / 🕳️ vacío de mercado** = no operes (ver abajo).

### 📐 Modo (Oscillate / Slide) — **no es solo etiqueta**
El bot mide con el **ADX** si hay tendencia o rango, y **cambia el peso de sus
indicadores** en consecuencia:
- **📈 Slide (tendencia)** → da más peso a MACD/medias (seguir la corriente).
- **🔁 Oscillate (rango)** → da más peso a los rebotes techo/piso (RSI/Bollinger).
- **🔀 mixto** → pesos equilibrados.

### 🎯 Alineación (0–100%)
Porcentaje de temporalidades que coinciden en la misma dirección. Es tu medida
de **confianza**: 80% significa que 4 de cada 5 "relojes" apuntan igual.

### 🧭 Lectura
Explicación en palabras de *por qué* el bot ve esa dirección (qué indicadores lo
apoyan). Sirve para que aprendas a leer el mercado, no solo a obedecer.

### 🕯️ Patrones (la forma de la vela)
- **Doji** → indecisión (fuerzas empatadas) → el bot fuerza NO OPERAR.
- **Martillo** → rechazo de mínimos (empuje al alza).
- **Estrella fugaz** → rechazo de máximos (empuje a la baja).
- **Marubozu** → momento fuerte en una dirección.
- **Envolvente alcista/bajista** → posible reversión.

### 📏 VWAP (precio "justo" de los profesionales)
- **por ENCIMA** → los compradores mandan (sesgo alcista).
- **por DEBAJO** → los vendedores mandan (sesgo bajista).
- El **%** es lo lejos que está el precio de ese nivel justo.
- *Nota honesta:* en OTC no hay volumen real; se pondera por **actividad (ticks)**.

### 🧱 Techo / Piso (soporte y resistencia)
Los niveles donde el precio suele **rebotar** (piso) o **rechazar** (techo).
- Cerca del **piso** → posible rebote al alza (CALL).
- Cerca del **techo** → posible rechazo a la baja (PUT).
En el **gráfico** se dibujan como líneas punteadas: verde = piso, roja = techo.

### 🔎 Panel de tiempos
Cada temporalidad (15s, 1m, 5m, …) con su color:
🟢 fuerte · 🟡 medio · ⚪ débil/neutral. La **entrada** manda en el tiempo corto;
la **tendencia** la confirma el tiempo largo.

### ⏱️ Timing
En binarias, la entrada correcta es **al abrir la vela**. Te dice cuántos
segundos faltan para la próxima.

### 💵 Pago (payout)
El % que paga Pocket Option por ese activo. **Si es bajo (< 80%)** el bot te
avisa: aunque aciertes, el valor de cada operación es peor (tu regla: no entrar
a activos con pago bajo).

---

## Alertas de PROTECCIÓN (cuando aparecen, NO operes)

| Alerta | Qué significa |
|---|---|
| 🛡️ **Mercado raro** | Spike, congelado o estallido de volatilidad (posible manipulación). |
| 🔄 **Indecisión** | La señal acaba de cambiar de dirección; espera a que se estabilice. |
| 🕳️ **Vacío de mercado** | El feed de precios tiene huecos o está congelado; los datos no son fiables. |
| 🕯️ **Doji** | La vela actual es de indecisión pura. |
| 😴 **Mercado plano** | El precio casi no se mueve; cualquier señal sería ruido. |

**Plano vs Vacío (importante):**
- **Plano** = *sí* llegan precios, pero no se mueven.
- **Vacío** = *no* llegan precios (el feed se cortó). Más peligroso.

---

## 🎓 Umbral aprendido
Si aparece, es el nivel de confianza que la **calibración** aprendió del historial
de ese activo, junto al win-rate histórico de esa configuración. El bot ajusta
solo sus exigencias según lo que ha ido viendo.

---

## Regla de oro
Si dudas, **NO operes**. El bot está diseñado para que "no operar" sea una
respuesta válida y frecuente. Menos operaciones, pero más claras, es mejor que
muchas operaciones confusas.
