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
  python -m bot.download_history --all            # TODOS los OTC, de 5 en 5
  python -m bot.download_history --all --batch 10 # todos, de 10 en 10

Por LOTES: exporta a datasets/ tras CADA lote (no se pierde el avance si se
corta) y REANUDA saltando los activos que ya están completos (>=5000 velas M1).

Guarda en history.db y exporta a datasets/. Honesto: baja lo que Pocket Option
sirva hacia atrás (suele ser miles de velas por temporalidad); nada inventado.
"""

import asyncio

# Un activo con al menos esto en M1 se considera ya descargado (para reanudar).
COMPLETO_M1 = 5000

# Majors OTC por defecto (rápido). Pasa otros como argumentos.
OTC_MAJORS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
              "USDCAD_otc", "AUDCAD_otc", "EURJPY_otc", "GBPJPY_otc",
              "EURGBP_otc", "USDCHF_otc"]

# Rango COMPLETO: de 5s a 1 día. PO dará lo que tenga en cada uno (se detiene solo).
PERIODOS = [(5, "5s"), (10, "10s"), (15, "15s"), (30, "30s"),
            (60, "1m"), (120, "2m"), (180, "3m"), (300, "5m"), (600, "10m"),
            (900, "15m"), (1800, "30m"), (3600, "1h"), (7200, "2h"),
            (14400, "4h"), (86400, "1d")]


def _lotes(lista, n):
    """Parte una lista en trozos de tamaño n (para bajar de 5 en 5, etc.)."""
    for i in range(0, len(lista), max(1, int(n))):
        yield lista[i:i + int(n)]


async def _descargar_uno(svc, asset, espera=1.3, pausa=3):
    """Baja TODAS las temporalidades (5s..1d) de un activo, hacia atrás."""
    if not svc.client.is_connected:           # esperar reconexión si se cayó
        await svc.client.wait_connected(timeout=30)
    try:
        await svc.client.set_asset(asset, 60)  # punto de partida del escaneo
    except Exception:
        pass
    await asyncio.sleep(pausa)
    for period, label in PERIODOS:
        try:
            total = await svc.scan_backwards(asset, period=period,
                                             max_days=365, paginas=40,
                                             espera=espera)
            print(f"   {label}: {total} velas", flush=True)
        except Exception as e:
            print(f"   {label}: error ({e})", flush=True)


async def _run(assets, do_all=False, batch=5):
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
    arranque = (assets[0] if assets else "EURUSD_otc")
    asyncio.create_task(svc.client.run(asset=arranque, period=60))
    print("Conectando a Pocket Option...", flush=True)
    # Esperar la conexión REAL (no un sleep a ciegas) + un momento para autenticar.
    if not await svc.client.wait_connected(timeout=30):
        print("No se pudo conectar a Pocket Option. Revisa ssid.txt.", flush=True)
        return
    await asyncio.sleep(4)                      # dar tiempo a autenticar + updateAssets

    # --all: descubrir TODOS los OTC de la lista que envía PO (updateAssets).
    if do_all:
        otc = sorted(s for s in svc._payouts if isinstance(s, str)
                     and s.endswith("_otc"))
        if otc:
            assets = otc
            print(f"Descubiertos {len(assets)} activos OTC. Bajando de "
                  f"{batch} en {batch}.", flush=True)
        else:
            print("No llegó la lista de activos; uso los majors por defecto.",
                  flush=True)
            assets = list(OTC_MAJORS)

    lotes = list(_lotes(assets, batch))
    for li, lote in enumerate(lotes, 1):
        print(f"\n=== Lote {li}/{len(lotes)}: {', '.join(lote)} ===", flush=True)
        for asset in lote:
            ya = svc.repo.count(asset, "M1")
            if ya >= COMPLETO_M1:              # reanudar: no rebajar lo ya hecho
                print(f"[{asset}] ya tiene {ya} velas M1 -> saltado", flush=True)
                continue
            print(f"[{asset}] ...", flush=True)
            await _descargar_uno(svc, asset)
        n = export_db(svc.repo)                 # exporta TRAS CADA lote (no se pierde)
        print(f"--- Lote {li} listo. Exportados {n} archivos a datasets/ ---",
              flush=True)

    print(f"\nDescarga completa ({len(assets)} activos). "
          f"SUBIR_HISTORIAL para la nube.", flush=True)
    try:
        svc.client.stop()
    except Exception:
        pass


def _main():
    import sys
    argv = sys.argv[1:]
    do_all = "--all" in argv
    batch = 5
    if "--batch" in argv:
        try:
            batch = int(argv[argv.index("--batch") + 1])
        except (IndexError, ValueError):
            batch = 5
    assets = [a for a in argv if not a.startswith("--") and not a.isdigit()]
    assets = assets or OTC_MAJORS
    asyncio.run(_run(assets, do_all=do_all, batch=batch))


if __name__ == "__main__":
    _main()
