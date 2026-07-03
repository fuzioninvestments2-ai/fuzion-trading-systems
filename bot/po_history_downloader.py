"""
bot/po_history_downloader.py
===========================
Descarga MASIVA de historial OTC de Pocket Option usando la librería de la
comunidad BinaryOptionsToolsV2 (que ya tiene el protocolo resuelto), y lo guarda
en la MISMA base de datos del bot para que el análisis lo use.

⚠️ IMPORTANTE — ejecutar SEPARADO del bot: esta librería abre su PROPIA conexión
con tu SSID. Si el bot ya está corriendo (otra conexión con el mismo SSID),
Pocket Option puede rechazar una. Así que:
  1) APAGA el bot (cierra su ventana).
  2) Corre esto: python -m bot.po_history_downloader
  3) Cuando termine, arranca el bot: ya tendrá el historial.

Correcciones sobre el script original del usuario (según la API real):
  - Lista de activos: active_assets() (no get_available_assets()).
  - get_candles(asset, period, offset): period = SEGUNDOS de historia a traer;
    offset = tamaño de vela en segundos (60 = 1m). La librería pagina sola.

Honesto: se descarga lo que Pocket Option realmente sirva (puede ser meses, no
años). Nada inventado — son SUS velas reales.

SRP: solo descarga y guarda. Requiere: pip install BinaryOptionsToolsV2.
"""

import os

# Temporalidades a descargar y CUÁNTOS DÍAS de historia pedir de cada una.
# Clave: segundos de la vela. Valor: días hacia atrás. (Se puede ajustar.)
DIAS_POR_TF = {
    60: 30,      # 1m  -> 30 días
    180: 60,     # 3m  -> 60 días
    300: 90,     # 5m  -> 90 días
    900: 180,    # 15m -> 180 días
    1800: 365,   # 30m -> 1 año
}


def _tf_key(tf_seconds):
    """Clave en la BD: 60 -> 'M1'; el resto -> 'tf<segundos>' (como el bot)."""
    return "M1" if tf_seconds == 60 else f"tf{tf_seconds}"


def _to_candles(velas):
    """
    Convierte la lista de velas de la librería (dicts time/open/high/low/close)
    al formato del bot (timestamp en ms + volume). Testeable sin red.
    """
    filas = []
    for v in velas or []:
        if not isinstance(v, dict):
            continue
        try:
            t = float(v.get("time"))
            o = float(v["open"]); h = float(v["high"])
            lo = float(v["low"]); c = float(v["close"])
        except (TypeError, ValueError, KeyError):
            continue
        ts_ms = int(t * 1000) if t < 1e12 else int(t)     # seg o ms -> ms
        filas.append({"timestamp": ts_ms, "open": o, "high": h,
                      "low": lo, "close": c,
                      "volume": float(v.get("volume", 0) or 0)})
    return filas


async def download_asset(client, repo, asset, dias_por_tf=None, logger=None):
    """Descarga todas las temporalidades de UN activo y las guarda. Devuelve total."""
    import logging
    log = logger or logging.getLogger("po_downloader")
    dias = dias_por_tf or DIAS_POR_TF
    total = 0
    for tf, ndias in dias.items():
        period = int(ndias) * 86400          # segundos de historia a traer
        try:
            velas = await client.get_candles(asset, period, tf)
        except Exception:
            log.exception("get_candles falló para %s tf=%s", asset, tf)
            continue
        filas = _to_candles(velas)
        if filas:
            repo.record_many(asset, _tf_key(tf), filas)
            total += len(filas)
            log.info("%s %s: %d velas", asset, _tf_key(tf), len(filas))
    return total


async def _run(assets=None, solo_otc=True):
    import logging
    from bot.history import HistoryRepository
    from bot.pocket_probe import _load_ssid
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("po_downloader")

    ssid = _load_ssid()
    if not ssid:
        log.error("Falta ssid.txt. Ponlo en la raíz del proyecto.")
        return
    try:
        from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
    except ImportError:
        log.error("Falta la librería. Instala: pip install BinaryOptionsToolsV2")
        return

    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "history.db")
    repo = HistoryRepository(db)

    client = PocketOptionAsync(ssid=ssid)
    try:
        await client.connect()
    except Exception:
        pass                                  # algunas versiones conectan solas
    try:
        await client.wait_for_assets(timeout=60)
    except Exception:
        pass

    # Lista de activos: los que pidan, o TODOS los OTC activos.
    if not assets:
        try:
            act = await client.active_assets()
            assets = [a.get("symbol") for a in act
                      if isinstance(a, dict) and a.get("symbol")]
            if solo_otc:
                assets = [a for a in assets if a.endswith("_otc")]
        except Exception:
            log.exception("No se pudo obtener la lista de activos")
            assets = ["EURUSD_otc"]

    log.info("Descargando historial de %d activos a %s ...", len(assets), db)
    for i, asset in enumerate(assets, 1):
        n = await download_asset(client, repo, asset, logger=log)
        log.info("[%d/%d] %s -> %d velas totales", i, len(assets), asset, n)

    try:
        await client.shutdown()
    except Exception:
        pass
    log.info("🎉 Descarga completa. Arranca el bot: ya tiene el historial.")


def _main():
    import sys
    import asyncio
    assets = sys.argv[1:] or None            # opcional: activos concretos
    asyncio.run(_run(assets=assets))


if __name__ == "__main__":
    _main()
