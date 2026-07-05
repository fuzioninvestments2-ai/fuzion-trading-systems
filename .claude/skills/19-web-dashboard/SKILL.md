---
name: 19-web-dashboard
description: Panel web de SOLO LECTURA para ver señales, progreso de datos y aciertos — uno por proyecto (OTC y Real por separado). Úsalo cuando el usuario diga "panel web", "dashboard", "ver en el navegador", "tablero de señales", "monitor visual", o al pensar en una interfaz aparte de Telegram.
---

# 19 · Panel web (dashboard de SOLO LECTURA)

Interfaz visual en el navegador para VER lo que el bot ya produce: última señal,
progreso de descarga, historial de aciertos. **Solo lectura**: muestra, no opera
(no coloca órdenes, coherente con `06`). Hoy la interfaz viva es Telegram; el
panel sería un extra que lee las mismas fuentes.

## De dónde saca los datos (sin red, sin tocar la cuenta)
- **Progreso** (`bot/progreso.py`): cuántas velas por tiempo/activo van acumuladas.
- **Señales** (`signal_log` en `history*.db`): últimas señales y su acierto/fallo.
- **Estado**: conexión, activo en foco, payout.
Todo eso ya existe; el panel solo lo presenta.

## Dos proyectos, dos paneles SEPARADOS
Igual que el resto, NO se cruzan:
- **OTC** → lee `fuzion-otc` (`history.db`, datasets OTC). Ver `proyecto-otc`.
- **Real** → lee `fuzion-real` (`history_real.db`, datasets Real). Ver `proyecto-real`.
Cada bot levanta su panel en su carpeta y su puerto; nunca comparten base.

## Cómo se construiría (si se pide)
- Servidor local mínimo (stdlib `http.server` o Flask) que sirve una página que
  consulta el repo (`HistoryRepository`) y `progreso`. Local, sin exponer a
  internet (nada de abrir puertos públicos ni evadir bloqueos).
- Robustez (Regla 3) y su `test_*.py` sin red (render con datos de ejemplo).
- Reutiliza el cálculo existente (Regla 1): el panel NO recalcula señales, las lee.

## Probar (las fuentes que alimentarían el panel)
```bash
python bot/test_progreso.py
python bot/test_signal_log.py
python bot/test_history.py
```
