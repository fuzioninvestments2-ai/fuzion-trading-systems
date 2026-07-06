---
name: 12-multi-pair-manager
description: Quantum Trading Core · Escaneo de múltiples pares aplicando el filtro cuántico a cada uno; solo pasa al Motor (Skill 04) el que supere el filtro rápido (Skill 05). Úsalo cuando el usuario diga "los pares", "muchos activos", "escanear todos", "el menú de activos".
---

# 12 · Multi-par (escaneo con filtro cuántico)

El sistema lee muchos pares. OTC: los `_otc` de PO (114+). REAL: 22 pares forex.

## Iterar y filtrar
Sobre la watchlist (`bot/profiles.py`: `OTC_MAJORS`, `REAL_MAJORS`), por cada par:
1. Filtro rápido (Skill 05): payout, datos completos, no pegado a S/R.
2. Solo si pasa → Motor Cuántico (Skill 04) calcula probabilidad + convergencia.
3. Se prioriza el par con mayor convergencia/probabilidad.
- `bot/collector.py` — foco: el análisis prioriza el par pedido; el colector cede.
- `bot/signal_menu.py` — menú de activos alfabético, 3 por fila; mercados aislados
  por bot (real no ve OTC). `bot/download_history.py` — descarga todos por lotes.

## Reglas
- Un activo por foco a la vez (una conexión por SSID).
- "Analizar de nuevo" lleva activo+tiempo en su dato (funciona tras reiniciar).

## Probar
```bash
python bot/test_signal_menu.py
python bot/test_profiles.py
```
