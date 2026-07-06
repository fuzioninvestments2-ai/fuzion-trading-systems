---
name: 01-api-connection
description: Quantum Trading Core · Conexión a Pocket Option (websocket, reconexión, SSID) y detección de Soportes/Resistencias para no operar pegado a niveles clave. Úsalo cuando el usuario diga "no conecta", "SSID", "reconectar", "soportes/resistencias", "pegado al techo/piso".
---

# 01 · Conexión + Soportes/Resistencias (Quantum Trading Core)

Conexión SOLO LECTURA a Pocket Option (no coloca órdenes) + la REGLA DE ORO de S/R.

## Conexión
- `bot/pocket_client.py` — websocket socket.io v4, `run()` reconecta con backoff,
  `forzar_reconexion()` (reinicio interno), `set_asset()`, `is_connected`.
- `bot/pocket_service.py` — orquesta la conexión + colector. `bot/pocket_probe._load_ssid`.

## `validate_safe_entry(symbol)` — S/R (últimos 50 highs/lows)
Implementado en el flujo cuántico (`bot/levels.detect_levels` + chequeo de pips en
`pocket_service.veredicto_sistema` / `cuantico.validate_signal_90`):
- Distancia del precio a la S/R más cercana. Pip = 0.0001 (0.01 en pares JPY).
- Si distancia **< 15 pips** → `cerca_sr = True` → **NO OPERAR** (aborta la señal).

## Probar
```bash
python bot/test_reconexion_interna.py
python bot/test_levels.py
```
Regla: NUNCA evasión de IP/VPN ni anti-detección.
