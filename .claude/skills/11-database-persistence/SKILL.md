---
name: 11-database-persistence
description: Persistencia (sqlite): historial de velas, registro de señales y aprendizaje, separado por bot. Úsalo cuando el usuario diga "la base de datos", "se pierde el historial", "no persiste", "history.db", "respaldar el aprendizaje", o al tocar history / signal_log.
---

# 11 · Persistencia (base de datos)

Dónde se guarda todo entre reinicios. Cada bot tiene SU base (no se cruzan).

## Archivos y bases
- `bot/history.py` — `HistoryRepository` (sqlite). Velas por (activo, tf). Clave
  `M1` para 60s, `tf<seg>` el resto.
- OTC → `history.db` · REAL → `history_real.db` (perfiles en `bot/profiles.py`).
- `bot/signal_log.py` — `SignalTracker`: registra cada señal y resuelve su
  resultado (aprendizaje real). Vive en la misma BD.

## Persistencia y nube
- `history.db` PERSISTE entre reinicios (archivo local), pero está en `.gitignore`
  → NO se sube a la nube. Lo que SÍ se respalda son los `datasets/` (`dataset_export`).
- El aprendizaje (señales resueltas) vive en la BD local: si se pierde la carpeta,
  se pierde. Para respaldarlo habría que exportarlo también (ver `02-market-data`).

## Reglas
- INSERT OR REPLACE por timestamp: no duplica velas.
- BD por bot para no mezclar OTC con real.

## Probar
```bash
python -m bot.test_history
python -m bot.test_signal_log
```
