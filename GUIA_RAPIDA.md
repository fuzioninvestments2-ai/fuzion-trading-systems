# Fuzion FX — Guía rápida (todo en una página)

Bot de SEÑALES educativas (demo, solo lectura, no coloca órdenes). Vos das el
visto bueno y operás en Pocket Option. El acierto no está garantizado.

## 1) Los dos únicos botones que necesitás

| Querés… | Doble clic en |
|---|---|
| **Actualizar y arrancar** (baja lo último y arranca limpio) | `ACTUALIZAR.bat` |
| Solo arrancar (sin actualizar) | `FUZION.vbs` (o el icono **Fuzion FX** del escritorio) |
| Ver si está corriendo | `ESTADO_FUZION_FX.bat` |
| Ver por qué no hay señales ahora | `POR_QUE_NO_HAY_SENALES.bat` |

No hace falta pegar nada en PowerShell. **`ACTUALIZAR.bat` es EL botón.**

> Cualquier archivo tipo `parche_v25.py`, `p25.b64`, etc. NO es del proyecto:
> borralo. Todo se actualiza solo con `ACTUALIZAR.bat`.

## 2) Cómo leer una señal (la tarjeta trae TODO)

```
🟩 CALL (poner ARRIBA)
🔥 FUERZA: FUERTE (68%)         <- de un vistazo: 🔥 fuerte / ✅ buena / ➖ débil
⏰ HORA DE ENTRADA: 22:50
⌛ VENCE: 22:51  (1 min - M1)
💰 Pago del activo: 70%          <- solo manda pares 53%-92%
🎛️ Indicadores: EMA↑ RSI• MACD↑ BB↓   <- los 4, con su dirección
🔭 Confluencia: 6/6 tiempos (1m↑,2m↑,...) conv 68%  <- la foto completa
```

**Regla simple**: entrá a las **🔥 FUERTE** y **✅ BUENA**; salteá las **➖ débil**.

## 3) Señales ordenadas (de a una)

Después de cada señal, el sistema espera a que **termine** + **10 minutos** antes
de mandar la siguiente. No hay ráfagas. (Se ajusta en `config/bots.yaml`,
`signal_cooldown_seconds`.)

## 4) Modos (desde el panel, botón "Modo")

- **⚡ rápido**: más señales (nunca contra la foto completa).
- **⚖ normal**: la foto completa debe confirmar.
- **🐢 lento**: pocas y muy seguras.

Se cambia en vivo, sin reiniciar.

## 5) Si algo no anda

1. Doble clic en `ESTADO_FUZION_FX.bat` → deben salir los 6 procesos CORRIENDO.
2. Si no, doble clic en `ACTUALIZAR.bat` (reinicia limpio).
3. Si sigue sin señales, `POR_QUE_NO_HAY_SENALES.bat` te dice el motivo exacto
   (sin velas / sin pago en banda / etc.).

## 6) Verificar que el código está sano

Doble clic en `AUTO_TEST.bat` → tiene que decir **33/33 OK**.
