---
name: 08-notifications
description: El bot de Telegram y la TARJETA de señal (menús, botones, chart, hora de entrada, lectura completa). Úsalo cuando el usuario diga "la tarjeta", "hora de entrada", "no sale el gráfico", "el menú de Telegram", "arrancar el bot", "cambiar el token", o al tocar telegram_signals / signal_menu.
---

# 08 · Notificaciones (Telegram + tarjeta de señal)

La interfaz: menús con botones y la tarjeta que ve el trader. Punto de entrada:
`bot.telegram_signals.run(perfil)`.

## Arquitectura de DOS bots (no se cruzan)
| Pieza | OTC | REAL |
|---|---|---|
| Carpeta | `fuzion-otc` | `fuzion-real` |
| Token (.env) | `TELEGRAM_BOT_TOKEN_OTC` | `TELEGRAM_BOT_TOKEN_REAL` |
| Cuenta/SSID | `ssid_otc.txt` | `ssid_real.txt` |
| Lanzador | `INICIAR_OTC.bat` | `INICIAR_REAL.bat` |

Cada `.bat` usa `%~dp0` (su propia carpeta) y hace `git pull` al arrancar. El token
va en el `.env` de CADA carpeta. Ojo: el token distingue mayúsculas (una letra mal
= "Invalid token"); copiarlo EXACTO, no re-escribir.

## Archivos
- `bot/telegram_signals.py` — `run()`, `_do_analysis` (rutea la tarjeta según
  `profile.usa_sistema`), `_format_deep` (tarjeta completa), envío de foto+pie.
- `bot/signal_menu.py` — menús mercado → activo → tiempo.
- `bot/chart.py` — dibuja el gráfico de velas (matplotlib).

## Tarjeta COMPLETA (lo que quiere el trader)
Chart + ALERTA (manipulación) + Modo/ADX + alineación fractal + Lectura + panel de
tiempos con % + **⏱️ Entra a las HH:MM:SS** (hora de entrada) + Pago + Mejores
indicadores + Historial. La produce el motor clásico (`analyze` + `_format_deep`);
para OTC se activa con `OTC_PROFILE.usa_sistema=False` en `bot/profiles.py`.

## Probar / arrancar
```bash
python -m bot.test_signal_menu
.\INICIAR_OTC.bat        # Windows (doble clic también)
```
