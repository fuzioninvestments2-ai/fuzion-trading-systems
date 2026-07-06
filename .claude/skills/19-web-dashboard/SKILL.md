---
name: 19-web-dashboard
description: Quantum Trading Core · Dashboard web de SOLO LECTURA (Streamlit/Flask) con el Panel Cuántico en vivo, equity curve y estado — uno por proyecto. PENDIENTE (diseño). Úsalo cuando el usuario diga "panel web", "dashboard", "Streamlit", "ver en el navegador".
---

# 19 · Panel web (dashboard de SOLO LECTURA) — DISEÑO

Interfaz visual en el navegador para VER lo que el sistema produce: el Panel
Cuántico (Skill 10), equity curve (señales resueltas del Skill 11), estado del bot
y botones Pausa/Stop. **Solo lectura del análisis**: no coloca órdenes (Skill 06).
Estado: PENDIENTE — hoy la interfaz viva es Telegram (Skill 08); esto es el diseño.

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
