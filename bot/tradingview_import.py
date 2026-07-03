"""
bot/tradingview_import.py
=========================
Importa a la base del bot un CSV EXPORTADO oficialmente desde TradingView
(función "Exportar datos del gráfico…", disponible en cuentas de pago). Es una
vía LEGÍTIMA: usas una función que pagas, no scraping.

⚠️ HONESTIDAD: aquí NO se automatiza el acceso a TradingView (iniciar sesión con
tus credenciales para "chupar" datos viola su ToS y puede BANEAR tu cuenta). El
flujo es: tú exportas el CSV desde TradingView → este script lo importa. Solo
para activos REALES (no OTC; los OTC son sintéticos de PO).

Formato esperado (típico de TradingView): una fila de cabecera y columnas que
incluyen time/date, open, high, low, close y (opcional) Volume. El campo de
tiempo puede venir como UNIX (segundos) o como fecha ISO. Robusto a variaciones
de mayúsculas y de orden de columnas.

Uso:
  python -m bot.tradingview_import EURUSD tf3600 "C:\\ruta\\EURUSD_1h.csv"
  python -m bot.tradingview_import XAUUSD M1   "C:\\ruta\\oro_1m.csv"

`clave` (tf): M1 = 1m; el resto tf<segundos> (tf300=5m, tf900=15m, tf1800=30m,
tf3600=1h, tf86400=1d) — igual que el resto del bot.
"""

import csv
import io


def _a_ms(valor):
    """
    Convierte el campo de tiempo a milisegundos. Acepta UNIX en segundos o ms, o
    una fecha ISO (2024-01-31 o 2024-01-31T10:00:00[Z/+00:00]). None si no puede.
    """
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    # 1) Numérico: UNIX en segundos (o ms si ya es grande).
    try:
        f = float(s)
        return int(f) if f >= 1e12 else int(f * 1000)
    except ValueError:
        pass
    # 2) Fecha ISO. Normaliza 'Z' y el espacio en vez de 'T'.
    from datetime import datetime, timezone
    iso = s.replace("Z", "+00:00").replace(" ", "T", 1)
    for fmt in (None,):  # intentamos fromisoformat, con y sin zona.
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            break
    # 3) Formatos comunes de fecha simple.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


def parse_tv_csv(texto):
    """
    Convierte el texto de un CSV de TradingView en la lista de velas del bot
    (dicts timestamp_ms/open/high/low/close/volume). Testeable SIN red.
    Ignora filas incompletas o con números inválidos.
    """
    filas = []
    lector = csv.reader(io.StringIO(texto))
    cabecera = None
    idx = {}
    for row in lector:
        if not row:
            continue
        if cabecera is None:
            cabecera = [c.strip().lower() for c in row]
            for i, nombre in enumerate(cabecera):
                idx[nombre] = i
            # Localiza columnas por nombre (robusto a orden/mayúsculas).
            col_t = next((idx[k] for k in ("time", "date", "datetime", "timestamp")
                          if k in idx), None)
            col_o = idx.get("open")
            col_h = idx.get("high")
            col_l = idx.get("low")
            col_c = idx.get("close")
            col_v = next((idx[k] for k in ("volume", "vol") if k in idx), None)
            if None in (col_t, col_o, col_h, col_l, col_c):
                # Cabecera no reconocible -> no seguimos (evita basura).
                return filas
            continue
        try:
            ts_ms = _a_ms(row[col_t])
            if ts_ms is None:
                continue
            o = float(row[col_o]); h = float(row[col_h])
            lo = float(row[col_l]); c = float(row[col_c])
        except (IndexError, ValueError):
            continue
        vol = 0.0
        if col_v is not None and col_v < len(row):
            try:
                vol = float(row[col_v])
            except ValueError:
                vol = 0.0
        filas.append({"timestamp": ts_ms, "open": o, "high": h,
                      "low": lo, "close": c, "volume": vol})
    return filas


def import_tv_file(asset, clave, ruta, repo, logger=None):
    """
    Lee el CSV de `ruta`, lo convierte y lo guarda en `repo` bajo (asset, clave).
    Rechaza activos OTC (no tienen fuente real). Devuelve nº de velas guardadas.
    """
    import logging
    log = logger or logging.getLogger("tradingview_import")
    if asset.endswith("_otc"):
        log.warning("%s es OTC: TradingView no aplica (usa la conexión de PO).",
                    asset)
        return 0
    try:
        with open(ruta, "r", encoding="utf-8-sig") as f:
            texto = f.read()
    except OSError as exc:
        log.error("No se pudo leer %s (%s)", ruta, exc)
        return 0
    velas = parse_tv_csv(texto)
    if velas:
        repo.record_many(asset, clave, velas)
    log.info("%s %s: %d velas importadas de TradingView.", asset, clave,
             len(velas))
    return len(velas)


def _main():
    import sys
    import os
    import logging
    from bot.history import HistoryRepository
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 4:
        print('Uso: python -m bot.tradingview_import ACTIVO CLAVE ruta.csv\n'
              '  ej: python -m bot.tradingview_import EURUSD tf3600 EURUSD_1h.csv')
        return
    asset, clave, ruta = sys.argv[1], sys.argv[2], sys.argv[3]
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "history.db")
    repo = HistoryRepository(db)
    n = import_tv_file(asset, clave, ruta, repo)
    print(f"Importadas {n} velas de {asset} ({clave}). "
          f"El bot ya las usará para el activo REAL.")


if __name__ == "__main__":
    _main()
