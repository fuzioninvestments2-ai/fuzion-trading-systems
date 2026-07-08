# datos/raw/ — CSV crudos de TradingView

Deja aquí los CSV que exportes de TradingView. El ingestor los convierte al formato
que lee el pipeline (`datasets/PAR__CLAVE.csv.gz`).

## Nombre de archivo: `PAR_TIMEFRAME.csv`
Ejemplos válidos: `EURUSD_1m.csv`, `EURUSD_5m.csv`, `GBPJPY_1h.csv`, `EURCAD_30m.csv`.

Timeframes soportados: **1m, 2m, 3m, 5m, 15m, 30m, 1h, 4h**
(el par puede llevar `-`; se limpia. Los `_otc` se rechazan: no tienen fuente real.)

## Columnas (las de TradingView sirven tal cual)
`time/date`, `open`, `high`, `low`, `close`, `volume` — robusto a orden y mayúsculas;
la fecha puede ser UNIX o ISO.

## Flujo completo
```bash
python -m bot.ingest_tradingview                       # datos/raw → datasets/
python -m bot.estudio_fx --pairs all --timeframes 1m,2m,3m,5m,15m,30m,1h
python -m bot.skills.backtest_ensemble --pairs all --timeframes 1m,2m,3m,5m
```

> Los CSV de esta carpeta NO se suben a git (son crudos y pesados). Lo que se sube
> es el resultado ingerido en `datasets/`.
