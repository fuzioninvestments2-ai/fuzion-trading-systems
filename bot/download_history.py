"""
bot/download_history.py
======================
Descarga el historial hacia ATRÁS usando la conexión PROPIA del bot
(pocket_client + scan_backwards) — la que SÍ funciona (la librería externa
BinaryOptionsToolsV2 no devolvía velas). Standalone, SIN Telegram.

Uso (con el bot de Telegram APAGADO, para no tener dos conexiones):
  python -m bot.download_history                 # majors OTC
  python -m bot.download_history EURUSD_otc       # activos concretos
  python -m bot.download_history EURUSD GBPUSD    # reales (sin _otc)

Guarda en history.db y exporta a datasets/. Honesto: baja lo que Pocket Option
sirva hacia atrás (suele ser miles de velas por temporalidad); nada inventado.
"""

import asyncio

# Majors OTC por defecto (rápido). Pasa otros como argumentos.
OTC_MAJORS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
              "USDCAD_otc", "AUDCAD_otc", "EURJPY_otc", "GBPJPY_otc",
              "EURGBP_otc", "USDCHF_otc"]

# Rango COMPLETO: de 5s a 1 día. PO dará lo que tenga en cada uno (se detiene solo).
PERIODOS = [(5, "5s"), (10, "10s"), (15, "15s"), (30, "30s"),
            (60, "1m"), (120, "2m"), (180, "3m"), (300, "5m"), (600, "10m"),
            (900, "15m"), (1800, "30m"), (3600, "1h"), (7200, "2h"),
            (14400, "4h"), (86400, "1d")]


async def _run(assets):
    from bot.pocket_service import PocketService
    from bot.pocket_probe import _load_ssid
    from bot.dataset_export import export_db

    ssid = _load_ssid()
    if not ssid:
        print("Falta ssid.txt en la raíz del proyecto.", flush=True)
        return

    svc = PocketService(ssid, demo=True)
    svc.connected = True
    svc._conn_lock = asyncio.Lock()
    # Arranca SOLO la conexión (no el colector), en segundo plano.
    asyncio.create_task(svc.client.run(asset=assets[0], period=60))
    print("Conectando a Pocket Option...", flush=True)
    # Esperar la conexión REAL (no un sleep a ciegas) + un momento para autenticar.
    if not await svc.client.wait_connected(timeout=30):
        print("No se pudo conectar a Pocket Option. Revisa ssid.txt.", flush=True)
        return
    await asyncio.sleep(3)

    for i, asset in enumerate(assets, 1):
        print(f"[{i}/{len(assets)}] {asset} ...", flush=True)
        # Si el socket se cayó entre activos, esperar a que reconecte.
        if not svc.client.is_connected:
            await svc.client.wait_connected(timeout=30)
        # Asegurar ticks para tener punto de partida del escaneo.
        try:
            await svc.client.set_asset(asset, 60)
        except Exception:
            pass
        await asyncio.sleep(3)
        for period, label in PERIODOS:
            try:
                total = await svc.scan_backwards(asset, period=period,
                                                 max_days=365, paginas=40)
                print(f"   {label}: {total} velas", flush=True)
            except Exception as e:
                print(f"   {label}: error ({e})", flush=True)

    n = export_db(svc.repo)
    print(f"\nExportados {n} archivos a datasets/  (SUBIR_HISTORIAL para la nube)",
          flush=True)
    print("Descarga completa. Arranca el bot: ya tiene el historial.", flush=True)
    try:
        svc.client.stop()
    except Exception:
        pass


def _main():
    import sys
    assets = sys.argv[1:] or OTC_MAJORS
    asyncio.run(_run(assets))


if __name__ == "__main__":
    _main()
