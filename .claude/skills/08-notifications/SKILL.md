---
name: 08-notifications
description: Quantum Trading Core · Telegram + TARJETA de señal (panel de tiempos, probabilidad, convergencia, hora de entrada) y aviso cuando se detecta 90%+ o se rechaza. Úsalo cuando el usuario diga "la tarjeta", "hora de entrada", "no sale el gráfico", "el menú", "el token".
---

# 08 · Notificaciones (Telegram + tarjeta cuántica)

Interfaz: menús con botones y la tarjeta que ve el trader. Entrada:
`bot.telegram_signals.run(perfil)`.

## `send_quantum_alert(signal_data)` → la tarjeta
`bot/telegram_signals._format_deep` arma la tarjeta con: panel de tiempos (dir/%),
**probabilidad** y **convergencia** del Motor Cuántico, **⏱️ hora de entrada**,
pago, y el MOTIVO si fue rechazada (ej. "convergencia 84% < 90%", "pegado a S/R").
Panel resumido en consola: `bot/cuantico.display_timeframe_panel(frames)`.

## Arquitectura de DOS bots (no se cruzan)
| Pieza | OTC | REAL |
|---|---|---|
| Carpeta | `fuzion-otc` | `fuzion-real` |
| Token (.env) | `TELEGRAM_BOT_TOKEN_OTC` | `TELEGRAM_BOT_TOKEN_REAL` |
| Cuenta/SSID | `ssid_otc.txt` | `ssid_real.txt` |
| Lanzador | `INICIAR_OTC.bat` | `INICIAR_REAL.bat` |

Cada `.bat` usa `%~dp0` y hace `git pull` al arrancar. Token EXACTO (distingue
mayúsculas). `bot/signal_menu.py` (menús), `bot/chart.py` (gráfico).

## Probar / arrancar
```bash
python bot/test_signal_menu.py
.\INICIAR_OTC.bat
```
