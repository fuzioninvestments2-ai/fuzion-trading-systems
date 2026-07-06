---
name: 05-protection
description: Protección del bot (NO ejecuta órdenes) — filtros que BLOQUEAN señales malas y barrera anti-basura. Úsalo cuando el usuario diga "payout bajo", "no operar en noticias", "sesiones", "mercado manipulado", "datos basura", "spread alto", o al tocar filtros / manipulation / void_detector / market_hours / payout / data_quality.
---

# 05 · Protección (filtros y barreras)

El equivalente sano a "gestión de riesgo" para un bot de SEÑALES: **no coloca
órdenes ni stop-loss** — PROTEGE bloqueando señales en condiciones malas. Esto es
lo que aporta disciplina.

## Qué bloquea (y por qué)
- **Payout** (`bot/payout.py`): el trader evita payout > 85% (zona peligrosa) y
  exige mínimo. `clasificar_payout()`.
- **Noticias** (`bot/news_filter.py`): en real, no operar antes/durante/después de
  noticias de alto impacto.
- **Sesiones/Horario** (`bot/market_hours.py`, `filtros.clasificar_sesion`):
  Londres/NY buenas; fuera de sesión el real calla.
- **Manipulación** (`bot/manipulation.py`): detecta velas "gigantes" fabricadas
  (spikes) → ALERTA "mercado raro, mejor NO operar".
- **Vacío/plano** (`bot/void_detector.py`): mercado congelado → cualquier señal es
  ruido → NO operar.
- **Spread** (real): > 2 pips bloquea.
- **Barrera anti-basura** (`bot/data_quality.py`): descarta series planas/NaN/
  corruptas/con saltos imposibles ANTES de leer (evita "sintonías absurdas").

## Regla de oro
Un "fallo" BLOQUEA la señal; un "aviso" solo informa. Ante duda de datos → callar.

## PUERTA DE CALIDAD estricta (`bot/validacion_senal.py`)
Además de los filtros de arriba, `validate_signal()` rechaza señales mediocres
(el foco es NO PERDER):
- **Indicadores en RUIDO**: si RSI/Estocástico/MACD/Bandas caen en **45-55%** →
  NO OPERAR (indecisión). Y cada uno debe estar ≥ **60%**.
- **Pegado a S/R**: si el precio está a **< 15 pips** de un soporte/resistencia
  reciente (últimos 50 highs/lows) → NO OPERAR (puede rebotar/rechazar).
- **Win-rate < 60%**, **alineación < 80%**, **umbral < 25%**, o **faltan tiempos**
  → NO OPERAR, con el motivo exacto.
Simular sobre señales reales: `python bot/simular_reglas.py fuzion-otc/history.db`.

## Probar
```bash
python -m bot.test_filtros
python -m bot.test_data_quality
python -m bot.test_news_filter
```
