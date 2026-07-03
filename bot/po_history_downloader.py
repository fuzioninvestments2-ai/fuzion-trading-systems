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

import asyncio
import os

# Pocos activos por defecto (majors) para que sea RÁPIDO. Con "todos" baja todos.
MAJORS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
          "USDCAD_otc", "USDCHF_otc", "EURJPY_otc", "GBPJPY_otc",
          "AUDCAD_otc", "EURGBP_otc"]

# Temporalidades a descargar y CUÁNTOS DÍAS de historia pedir de cada una.
# Clave: segundos de la vela. Valor: días hacia atrás. (Se puede ajustar.)
DIAS_POR_TF = {
    60: 7,       # 1m  -> 7 días  (periodos grandes hacían que PO no respondiera)
    180: 15,     # 3m  -> 15 días
    300: 30,     # 5m  -> 30 días
    900: 60,     # 15m -> 60 días
    1800: 90,    # 30m -> 90 días
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
    # Suscribir el símbolo primero: sin esto, get_candles suele quedarse esperando.
    try:
        await asyncio.wait_for(client.subscribe_symbol(asset), timeout=15)
        await asyncio.sleep(1.0)
    except Exception:
        pass
    total = 0
    for tf, ndias in dias.items():
        period = int(ndias) * 86400          # segundos de historia a traer
        velas = None
        # 1) get_candles(asset, period, offset=tamaño de vela). Con timeout.
        try:
            velas = await asyncio.wait_for(
                client.get_candles(asset, period, tf), timeout=20)
        except asyncio.TimeoutError:
            print(f"   {asset} {tf}s: get_candles timeout", flush=True)
        except Exception as e:
            print(f"   {asset} {tf}s: get_candles error ({e})", flush=True)
        # 2) Respaldo: history(asset, period=tamaño de vela) -> velas recientes.
        if not velas:
            try:
                velas = await asyncio.wait_for(client.history(asset, tf),
                                               timeout=20)
            except Exception:
                velas = None
        filas = _to_candles(velas)
        if filas:
            repo.record_many(asset, _tf_key(tf), filas)
            total += len(filas)
            print(f"   {asset} {_tf_key(tf)}: {len(filas)} velas", flush=True)
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
    await asyncio.sleep(4)                     # dejar que la conexión se estabilice
    try:
        await client.wait_for_assets(timeout=60)
    except Exception:
        pass
    print("Conectado. Empezando descarga...", flush=True)

    # Lista de activos:
    #  - sin argumentos -> MAJORS (rápido).
    #  - "todos"/"all"   -> TODOS los OTC activos.
    #  - nombres sueltos -> esos.
    if not assets:
        assets = list(MAJORS)
    elif len(assets) == 1 and assets[0].lower() in ("todos", "all"):
        try:
            act = await client.active_assets()
            assets = [a.get("symbol") for a in act
                      if isinstance(a, dict) and a.get("symbol")]
            if solo_otc:
                assets = [a for a in assets if a.endswith("_otc")]
        except Exception:
            log.exception("No se pudo obtener la lista de activos")
            assets = list(MAJORS)

    print(f"Descargando historial de {len(assets)} activos a {db} ...", flush=True)
    for i, asset in enumerate(assets, 1):
        print(f"[{i}/{len(assets)}] {asset} ...", flush=True)
        n = await download_asset(client, repo, asset, logger=log)
        print(f"   -> {n} velas", flush=True)

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
