---
name: 10-monitoring-logging
description: Monitoreo, progreso de datos, registro y auditoría del bot. Úsalo cuando el usuario diga "cuánto falta de descarga", "ver el progreso", "revisar los logs", "auditar los datos", "está trabajando el robot", o al tocar progreso / signal_log / auditoria / logs.
---

# 10 · Monitoreo y registro

Ver qué está haciendo el bot y si los datos están sanos, sin apagar nada.

## Archivos y usos
- `bot/progreso.py` — cuánto historial hay acumulado por activo/tiempo:
  ```bash
  python -m bot.progreso            # OTC
  python -m bot.progreso real       # REAL
  ```
- `bot/auditoria.py` — completitud (5 pasadas) y qué falta re-escanear:
  ```bash
  python -m bot.auditoria [real]
  ```
- `bot/signal_log.py` — historial de señales para medir win-rate real.
- `logs/` — salida de ejecución.

## Robot 24/7 (autónomo)
`ROBOT_AUTO.bat` (OTC) / `ROBOT_REAL.bat`: descargan/acumulan y suben a la nube
solos; si se caen, se REINICIAN. Reinicio interno de la conexión antes de molestar
al usuario (socket "vivo pero mudo").

## Watchdog
Si el historial no crece varias rondas: el acumulador fuerza una reconexión interna;
si aun así no crece, avisa que el SSID caducó (refrescarlo a mano).

## Probar
```bash
python -m bot.test_progreso
python -m bot.test_accumulator
```
