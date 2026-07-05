---
name: 12-multi-pair-manager
description: Manejo de MUCHOS pares a la vez (watchlist, foco, menú alfabético, descarga por lotes). Úsalo cuando el usuario diga "los pares", "muchos activos", "el menú de activos", "descargar todos", "cambiar de par rápido", o al tocar profiles.activos / signal_menu / collector.
---

# 12 · Multi-par (manejo de activos)

El bot lee muchos pares. OTC: los `_otc` que sirve PO (114+). REAL: 22 pares forex
(solo monedas).

## Archivos
- `bot/profiles.py` — watchlist por bot (`OTC_MAJORS`, `REAL_MAJORS`); REAL veta
  cripto/metales (`_NO_MONEDAS`).
- `bot/signal_menu.py` — menú de activos en **orden alfabético**, 3 por fila (rápido
  de navegar). Aísla mercados por bot (real no ve OTC y viceversa).
- `bot/collector.py` — foco: el análisis prioriza el par pedido; el colector cede.
- `bot/download_history.py` — descarga TODOS por lotes (`--all --batch 5`),
  reanudable (salta los ya completos).

## Reglas
- Un activo por foco a la vez (una conexión por SSID).
- El botón "Analizar de nuevo" lleva activo+tiempo en su dato (funciona tras reiniciar).

## Probar
```bash
python -m bot.test_signal_menu
python -m bot.test_profiles
```
