---
name: 11-database-persistence
description: Quantum Trading Core · Persistencia sqlite — velas (9 timeframes) y señales con su probabilidad/convergencia (columna meta) para alimentar el backtest y el win-rate del Skill 05. Úsalo cuando el usuario diga "base de datos", "no persiste", "history.db", "signals_log".
---

# 11 · Persistencia (base de datos)

Dónde se guarda todo entre reinicios. Cada bot tiene SU base (no se cruzan).

## Tablas
- **`candles`** (`bot/history.py` HistoryRepository): velas por (activo, tf). Clave
  `M1` para 60s, `tf<seg>` el resto. OTC → `history.db` · REAL → `history_real.db`.
- **`signals`** (`bot/signal_log.py` SignalTracker) = el `signals_log`: cada señal
  del Motor Cuántico con dirección, precio, expiración, resultado (win/loss/pendiente),
  votos y **`meta`** (JSON con alineación, probabilidad, convergencia, S/R, win-rate)
  → alimenta el backtest (Skill 09) y los filtros (Skill 05).

## Persistencia y nube
- `history.db` persiste local pero está en `.gitignore` (no se sube). Lo que se
  respalda son los `datasets/` (`bot/dataset_export.py`).
- INSERT sin duplicar por timestamp. BD por bot (OTC/real no se mezclan).

## Probar
```bash
python bot/test_history.py
python bot/test_signal_log.py
```
