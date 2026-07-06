---
name: 01-api-connection
description: Conexión en vivo a Pocket Option (websocket socket.io v4) con reconexión automática. Úsalo cuando el usuario diga "el bot no conecta", "se cae la conexión", "revisar el SSID", "reconectar", "arrancar la conexión a Pocket Option", o al tocar pocket_client / pocket_service.
---

# 01 · Conexión a Pocket Option (API en vivo)

Módulo de conexión del bot Fuzion. SOLO LECTURA: recibe precios/velas, **no coloca
órdenes**. Robustez = reconexión automática (Regla 3 del proyecto).

## Archivos
- `bot/pocket_client.py` — cliente websocket. Bucle `run()` reconecta con backoff;
  `forzar_reconexion()` cierra el socket "vivo pero mudo" para forzar reinicio interno;
  `wait_connected()`, `is_connected`, `set_asset()`, `load_history_period()`.
- `bot/pocket_service.py` — orquesta la conexión + colector integrado.
- `bot/pocket_probe.py` — `_load_ssid(nombre)` busca el SSID por bot (ssid_otc.txt /
  ssid_real.txt / ssid.txt). Nunca se versiona (gitignore).

## El SSID (llave de la cuenta)
Cada bot usa SU cuenta: OTC → `ssid_otc.txt`, REAL → `ssid_real.txt`. Es la línea
`42["auth",{...}]` copiada del navegador. Si caduca, el historial deja de crecer.

## Cómo probar (sin red)
```bash
python -m bot.test_reconexion_interna
python -m bot.test_scan_backwards
```
Resultado esperado: "TODOS OK" — el reinicio interno cierra/invalida el socket y el
escaneo sobrevive a caídas (1005) sin abortar.

## Acción del precio y S/R (desde el feed en vivo)
El feed da los precios con los que se detectan **soportes/resistencias recientes**
(últimos ~50 highs/lows, `bot/levels.detect_levels`). Con eso, la puerta de calidad
(`validate_signal`, skills 04/05) aplica la **REGLA DE ORO**: si el precio está a
**< 15 pips** de un soporte/resistencia ("pegado al techo/piso") → **NO OPERAR**,
esperar a que se aleje o rompa la zona. Pip = 0.0001 (0.01 en pares JPY).

## Reglas
- NUNCA evasión de IP/VPN ni anti-detección (riesgo de baneo de cuenta).
- Ante caída: esperar reconexión y reintentar; jamás abortar la descarga larga.
