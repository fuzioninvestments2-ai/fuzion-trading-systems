---
name: 02-market-data
description: Velas OHLC, historial y datasets del bot (descarga, acumulación 24/7, export/import a la nube). Úsalo cuando el usuario diga "descargar historial", "no hay datos / pocos datos", "acumular velas", "subir a la nube", "faltan velas", o al tocar candles / history / collector / download_history / datasets.
---

# 02 · Datos de mercado (velas, historial, datasets)

De dónde salen las velas que lee el bot. Solo datos reales (de Pocket Option o
fuentes legítimas); nada inventado ni emulado.

## Archivos
- `bot/candles.py` — `CandleBuilder`: arma velas OHLC desde ticks.
- `bot/history.py` — `HistoryRepository` (sqlite). Clave: `M1` para 60s, `tf<seg>`
  el resto (tf5, tf300...). BD PROPIA por bot (history.db / history_real.db).
- `bot/collector.py` — colector integrado: acumula historial en los ratos libres.
- `bot/download_history.py` — descarga profunda 5s→1d hacia atrás (por lotes,
  reanudable). `bot/accumulator.py` — acumula hacia adelante 24/7 + sube.
- `bot/dataset_export.py` — export/import datasets (`.csv.gz`). DETERMINISTA
  (gzip mtime=0): dato igual → bytes iguales → git no re-sube todo.
- `bot/cloud_push.py` — sube con REINTENTO pull+push (no se pierde la ronda).
- `bot/auditoria.py` — auditor de completitud (5 pasadas): existe, no basura, sin
  huecos, sin duplicados, completo. Lista lo PENDIENTE de re-escanear.

## Uso (bot de Telegram APAGADO — una conexión por SSID)
```bash
python -m bot.download_history --all --batch 5   # descarga profunda todos los OTC
python -m bot.dataset_export export OTC          # BD -> datasets/otc
python -m bot.auditoria                          # ¿qué falta?
```
Al arrancar en otra máquina/carpeta: `python -m bot.dataset_export import OTC`
(carga datasets → history.db, para que la tarjeta tenga datos al instante).

## Probar
```bash
python -m bot.test_dataset_export
python -m bot.test_auditoria
```
