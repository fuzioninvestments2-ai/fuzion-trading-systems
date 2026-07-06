---
name: 06-order-execution
description: Quantum Trading Core · LÍMITE de ejecución — el bot es de SEÑALES y NO coloca órdenes; cuando el Motor Cuántico (Skill 04) da OPERAR, la ejecución la hace el HUMANO. Úsalo cuando el usuario diga "que opere solo", "ejecutar la orden", "auto-trading", "que entre por mí".
---

# 06 · Ejecución de órdenes (LÍMITE del sistema)

Quantum Trading Core es un sistema de **SEÑALES, en demo, solo lectura**. Por regla
**no negociable** del proyecto (`CLAUDE.md`), **NO coloca órdenes**. Este skill
documenta el límite: cuando el Motor Cuántico (Skill 04) retorna `operate: True`, la
orden la coloca el HUMANO a mano (`execute_quantum_order` NO se implementa en vivo).

## Por qué el bot NO ejecuta (aunque se pueda)
- El propósito es **disciplina y protección**, no automatizar dinero. Ningún
  sistema gana siempre; automatizar entradas convierte una mala racha en pérdida
  rápida e incontrolada.
- Pocket Option OTC usa precios **sintéticos** que PO reinicia: un bot que opera
  solo sobre eso es especialmente frágil.
- Honestidad: el acierto real lo mide el **registro** (`signal_log`), no una
  promesa. El humano decide y aprieta el botón.

## Dónde para el bot y dónde entras TÚ
1. El motor produce la señal (dirección, alineación 7/12, hora de entrada).
2. La tarjeta de Telegram te muestra **cuándo** (hora de apertura de la vela) y
   **hacia dónde** (CALL/PUT), con el payout y los filtros de protección.
3. La **ejecución la haces tú**, a mano, en tu plataforma. El bot no toca tu cuenta.

## Si algún día quieres ejecución automática
Es un **cambio de propósito** del proyecto y un riesgo de dinero real. No se hace
en silencio. Requiere, como mínimo:
- Confirmación explícita e informada del dueño.
- Arrancar SOLO en **cuenta demo**, con **confirmación manual** por operación
  (nunca fuego automático), límites de pérdida y kill-switch.
Mientras esa decisión no exista, este skill se queda como **guardarraíl**.

## OTC vs Real
Igual para los dos proyectos: **ninguno** ejecuta. La diferencia (cuenta, token,
carpeta) la ven `proyecto-otc` y `proyecto-real`.

## Probar (que se cumple el límite)
El flujo EN VIVO (`telegram_signals` → `pocket_service`) no debe llamar a ninguna
orden. Existe un `place_order` como **mock de test** y en `run_demo.py` como puente
que a propósito NUNCA se llama (así está documentado). La comprobación honesta:
```bash
# En el servicio vivo NO debe haber llamada a colocar órdenes:
grep -rInE "place_order|open_trade|create_order" bot/pocket_service.py bot/telegram_signals.py \
  || echo "OK: el flujo vivo no coloca órdenes"
```
