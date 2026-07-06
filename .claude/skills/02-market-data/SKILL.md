---
name: 02-market-data
description: Quantum Trading Core · Datos OHLC de los 9 timeframes del sistema (5s,10s,15s,1m,2m,3m,5m,10m,15m) + historial/datasets. Úsalo cuando el usuario diga "faltan datos", "pocos datos", "descargar historial", "acumular velas", "subir a la nube".
---

# 02 · Datos de mercado (9 timeframes cuánticos)

Provee las velas OHLC de los **9 tiempos** del motor cuántico (5s → 15m). Solo datos
reales (de Pocket Option o fuentes legítimas); nada inventado.

## `fetch_quantum_data(symbol)` — en el código real
- `bot/pocket_service._frames_para_sistema(asset, sistema)` arma los frames FRESCOS
  de todos los tiempos y el motor los filtra a los 9 (`bot/cuantico.TIMEFRAMES_9`):
  ticks para sub-minuto, M1 y agregación (con vela en formación) para los mayores.
- **`data_complete`**: si un tiempo no tiene ≥20 velas, no entra → el motor lo trata
  como "faltan tiempos" (Skill 13) y NO OPERA.

## Archivos
- `bot/candles.py` (CandleBuilder), `bot/history.py` (sqlite: `M1`/`tf<seg>`),
  `bot/collector.py` (acumulación 24/7), `bot/download_history.py` (descarga profunda),
  `bot/dataset_export.py` (datasets .csv.gz deterministas), `bot/cloud_push.py`.
- Frescura OTC: `_recortar_sesion_otc` corta en el reset de PO (por precio o hueco de
  tiempo) → solo la sesión de AHORA (no se mezcla con velas viejas).

## Probar
```bash
python bot/test_candles.py
python bot/test_sesion_otc.py
```
