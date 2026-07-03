"""
bot/historical_loader.py
========================
Carga HISTORIAL REAL de mercado (años) para los activos REALES de Pocket Option
(Lun-Vie), desde fuentes LEGÍTIMAS y gratuitas: yfinance (Yahoo Finance).

EL PORQUÉ: los activos REALES de PO (EUR/USD, oro, BTC... fuera de OTC) tienen los
MISMOS precios que el mercado real. Así que su historia SÍ está disponible en
fuentes abiertas. Con años de datos, los tiempos largos (15m/30m) y el backtest
tienen base de sobra desde el primer momento.

⚠️ HONESTIDAD — dos límites que debes conocer:
  1) Esto sirve SOLO para activos REALES, NO para los OTC. Los OTC son sintéticos
     de Pocket Option y no existen en ninguna fuente externa (no se inventan).
  2) Los datos intradía gratuitos tienen rango limitado (yfinance: 1m ~7 días,
     5m/15m/30m ~60 días, 1h ~2 años, diario décadas). Suficiente para dar
     profundidad real a los tiempos del bot, aunque no sea "tick a tick de 10
     años". Nada de scraping a TradingView (va contra sus reglas): usamos su
     misma fuente de datos por vías permitidas.

SRP: solo descarga y guarda en el repositorio SQLite existente (mismo esquema).
"""

# Mapa de código REAL de Pocket Option -> ticker de Yahoo Finance.
PO_TO_YF = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURGBP": "EURGBP=X", "XAUUSD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
}

# Intervalos yfinance -> (clave en la BD, cuánto historial pedir).
# La clave debe coincidir con la que lee el análisis: 60s -> "M1"; el resto
# como "tf<segundos>" (tf300=5m, tf900=15m, tf1800=30m).
INTERVALOS = [
    ("1m", "M1", "7d"),
    ("5m", "tf300", "60d"),
    ("15m", "tf900", "60d"),
    ("30m", "tf1800", "60d"),
    ("1h", "tf3600", "730d"),      # 1h -> ~2 años (tiempos largos con base real)
    ("1d", "tf86400", "max"),      # diario -> décadas (sesgo mayor)
]


def yf_ticker(po_code):
    """Traduce un código real de PO (p.ej. 'EURUSD') al ticker de Yahoo Finance."""
    code = po_code.replace("_otc", "").replace("/", "").replace(" ", "").upper()
    return PO_TO_YF.get(code)


def _df_to_candles(df):
    """
    Convierte un DataFrame de yfinance (índice de fechas, columnas OHLC(V)) a la
    lista de velas del bot: dicts con timestamp(ms)/open/high/low/close/volume.
    Maneja columnas simples o MultiIndex (según versión de yfinance). Testeable.
    """
    velas = []
    cols = {str(c[0]).lower() if isinstance(c, tuple) else str(c).lower(): c
            for c in df.columns}
    o, h, l, c_, v = (cols.get("open"), cols.get("high"), cols.get("low"),
                      cols.get("close"), cols.get("volume"))
    if None in (o, h, l, c_):
        return velas
    for idx, row in df.iterrows():
        try:
            ts_ms = int(idx.timestamp() * 1000)
            open_ = float(row[o]); high = float(row[h])
            low = float(row[l]); close = float(row[c_])
        except (TypeError, ValueError, AttributeError):
            continue
        if open_ != open_ or close != close:      # NaN
            continue
        vol = 0.0
        if v is not None:
            try:
                vol = float(row[v])
                if vol != vol:
                    vol = 0.0
            except (TypeError, ValueError):
                vol = 0.0
        velas.append({"timestamp": ts_ms, "open": open_, "high": high,
                      "low": low, "close": close, "volume": vol})
    return velas


def load_real_history(po_code, repo, intervalos=None, logger=None):
    """
    Descarga el historial REAL de un activo y lo guarda en `repo`. Devuelve el
    total de velas guardadas. Requiere `pip install yfinance`.

    po_code: código del activo real (p.ej. 'EURUSD'). Si termina en '_otc' se
    rechaza (los OTC no tienen fuente externa real).
    """
    import logging
    log = logger or logging.getLogger("historical_loader")
    if po_code.endswith("_otc"):
        log.warning("%s es OTC (sintético): no hay fuente externa real.", po_code)
        return 0
    ticker = yf_ticker(po_code)
    if not ticker:
        log.warning("Sin mapeo de ticker para %s (añádelo a PO_TO_YF).", po_code)
        return 0
    try:
        import yfinance as yf
    except ImportError:
        log.error("Falta yfinance. Instálalo con: pip install yfinance")
        return 0

    total = 0
    for interval, key, period in (intervalos or INTERVALOS):
        try:
            df = yf.download(ticker, interval=interval, period=period,
                             progress=False, auto_adjust=False)
        except Exception:
            log.exception("Fallo al descargar %s %s", ticker, interval)
            continue
        if df is None or len(df) == 0:
            continue
        velas = _df_to_candles(df)
        if velas:
            repo.record_many(po_code, key, velas)
            total += len(velas)
            log.info("%s %s: %d velas guardadas (%s).", po_code, key,
                     len(velas), interval)
    return total


def _main():
    """CLI: python -m bot.historical_loader EURUSD GBPUSD XAUUSD ..."""
    import sys
    import os
    from bot.history import HistoryRepository
    logging_basic()
    codes = sys.argv[1:] or list(PO_TO_YF.keys())
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "history.db")
    repo = HistoryRepository(db)
    print(f"Descargando historial REAL de {len(codes)} activos a {db} ...")
    for code in codes:
        n = load_real_history(code, repo)
        print(f"  {code}: {n} velas")
    print("Listo. El bot usará este historial para los activos REALES.")


def logging_basic():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")


if __name__ == "__main__":
    _main()
