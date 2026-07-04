"""
bot/accumulator.py
==================
ACUMULADOR continuo: mantiene UNA conexión propia a Pocket Option (con el bot de
Telegram APAGADO) y va apilando historial HACIA ADELANTE. Cada ronda rota por los
activos, refresca las velas recientes de TODA la escalera (5s..1d) de cada uno y
deja que se formen velas nuevas en vivo. Al terminar cada ronda exporta a
datasets/ y, si se pide, lo sube a la nube (git push).

EL PORQUÉ: el escaneo hacia atrás (download_history) topa en el límite que PO
sirve (~5150 velas). La única forma HONESTA de tener MÁS historia es hacia
adelante: guardar lo que va llegando en vivo. Cuanto más corra, más profundo el
historial de los tiempos cortos. No se inventa nada.

Uso (bot de Telegram APAGADO — una sola conexión por SSID):
  python -m bot.accumulator                        # majors OTC, sin subir
  python -m bot.accumulator --push                 # además sube a la nube
  python -m bot.accumulator EURUSD_otc GBPUSD_otc   # activos concretos
  python -m bot.accumulator --push EURUSD_otc       # concretos + subir
"""

import asyncio

# Majors OTC por defecto. Pasa otros como argumentos.
OTC_MAJORS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
              "USDCAD_otc", "AUDCAD_otc", "EURJPY_otc", "GBPJPY_otc",
              "EURGBP_otc", "USDCHF_otc"]

# Escalera completa 5s..1d: en cada ronda pedimos las velas recientes de cada
# temporalidad para toparlas hacia adelante (PO responde con updateHistoryNewFast).
LADDER = [5, 10, 15, 30, 60, 120, 180, 240, 300, 600, 900, 1800,
          3600, 7200, 14400, 86400]

# Segundos que nos quedamos en cada activo dejando formar velas M1 en vivo.
SEG_POR_ACTIVO = 30


def _clave(period):
    """Clave en la BD: 60 -> 'M1'; el resto -> 'tf<segundos>' (como el bot)."""
    return "M1" if period == 60 else f"tf{period}"


def _cobertura(repo, asset):
    """
    Suma de velas en TODA la escalera 5s..1d y cuántas temporalidades tienen
    datos. Sirve para mostrar que se acumula todo el rango, no solo M1.
    """
    total = 0
    tiempos = 0
    for p in LADDER:
        c = repo.count(asset, _clave(p))
        total += c
        if c > 0:
            tiempos += 1
    return total, tiempos


def _git_push(logger):
    """
    Sube datasets/ a la nube. Defensivo: si git falla (sin credenciales, sin
    red), avisa y sigue — el acumulador NO se detiene por un fallo al subir.
    """
    import subprocess
    # PULL antes de PUSH: si la rama remota tiene commits que este PC no tiene
    # (p.ej. se trabaja en paralelo desde otra sesión), el push se rechaza. Con un
    # pull --no-rebase primero, se reconcilia y el push pasa. Los datasets son
    # archivos nuevos: no chocan con cambios de código.
    for cmd in (["git", "add", "datasets/"],
                ["git", "commit", "-m", "datos: acumulador (historial en vivo)"],
                ["git", "pull", "--no-rebase", "--no-edit"],
                ["git", "push"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            # 'commit' devuelve !=0 si no hay cambios: es normal, no es error.
            if r.returncode != 0 and cmd[1] not in ("commit", "pull"):
                logger.warning("git %s: %s", cmd[1], (r.stderr or "").strip()[:200])
        except Exception as exc:
            logger.warning("No se pudo %s (%s)", " ".join(cmd), exc)
            return


async def _accumulate_round(svc, assets, seg_por_activo=SEG_POR_ACTIVO,
                            verbose=True):
    """
    Una ronda: por cada activo refresca la escalera y acumula velas en vivo.
    Espera reconexión si el socket se cayó (no aborta). Imprime señales de vida
    por activo (verbose) para que no parezca congelado durante la ronda.
    """
    lock = svc._conn_lock or _nulllock()
    n = len(assets)
    for idx, asset in enumerate(assets, 1):
        if not svc.client.is_connected:
            if not await svc.client.wait_connected(timeout=30):
                svc.log.warning("acumulador: sin conexión, salto %s", asset)
                continue
        try:
            async with lock:
                await svc.client.set_asset(asset, 60)
                # Refresca las velas RECIENTES de toda la escalera (tope adelante).
                await svc.client.request_history(asset, LADDER)
                # Deja formar velas M1 en vivo un rato (historia hacia adelante).
                for _ in range(int(seg_por_activo)):
                    await asyncio.sleep(1)
            if verbose:
                # Señal de vida: total en TODA la escalera 5s..1d y cuántos
                # tiempos tienen datos (para ver que NO es solo M1).
                total, tiempos = _cobertura(svc.repo, asset)
                print(f"   · [{idx}/{n}] {asset}: {total} velas en {tiempos}/"
                      f"{len(LADDER)} tiempos (5s..1d)", flush=True)
        except Exception as exc:
            svc.log.warning("acumulador: salto %s (%s)", asset, exc)
            await asyncio.sleep(1)


class _nulllock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


async def _run(assets, push=False, rondas=None):
    """
    Bucle continuo. `rondas=None` -> infinito (Ctrl+C para parar). `rondas=N`
    (para pruebas/uso puntual) -> corre N rondas y sale.
    """
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
    asyncio.create_task(svc.client.run(asset=assets[0], period=60))
    print("Acumulador: conectando a Pocket Option...", flush=True)
    if not await svc.client.wait_connected(timeout=30):
        print("No se pudo conectar. Revisa ssid.txt.", flush=True)
        return
    await asyncio.sleep(3)

    print(f"Acumulando {len(assets)} activos (5s..1d) hacia adelante. "
          f"Ctrl+C para parar.", flush=True)
    ronda = 0
    total_prev = None
    sin_crecer = 0
    try:
        while rondas is None or ronda < int(rondas):
            ronda += 1
            await _accumulate_round(svc, assets)
            from bot.profiles import OTC_PROFILE
            n = export_db(svc.repo, out_dir=OTC_PROFILE.datasets_dir)  # datasets/otc
            total = sum(svc.repo.count(a, "M1") for a in assets)
            print(f"[ronda {ronda}] exportados {n} archivos · {total} velas M1 "
                  f"acumuladas", flush=True)
            # WATCHDOG: si el historial no crece, primero intento un REINICIO
            # INTERNO de la conexión (caso "socket vivo pero mudo": PO deja de
            # enviar sin cerrar). Yo mismo reinicio la conexión sin apagar el
            # proceso ni tocar el otro bot. Solo si NI AUN ASÍ crece, escalo a
            # "el SSID caducó" (eso sí es externo: hay que refrescarlo a mano).
            if total_prev is not None and total <= total_prev:
                sin_crecer += 1
            else:
                sin_crecer = 0
            total_prev = total
            if sin_crecer == 2:
                print("\n⟳ El historial no crece: reinicio la conexión por dentro "
                      "(sin apagar nada)...", flush=True)
                try:
                    if await svc.client.forzar_reconexion():
                        await svc.client.wait_connected(timeout=30)
                        await asyncio.sleep(3)     # re-autenticar
                except Exception as exc:
                    svc.log.warning("reinicio interno falló (%s)", exc)
            if sin_crecer >= 4:
                print("\n⚠️  El historial no crece ni tras reiniciar la conexión. "
                      "Lo más probable es que el SSID haya CADUCADO. Actualiza "
                      "ssid.txt (vuelve a copiar la línea 42[\"auth\",...] del "
                      "navegador) y reinicia.", flush=True)
            if push:
                _git_push(svc.log)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nAcumulador detenido por el usuario.", flush=True)
    finally:
        try:
            await svc.stop()
        except Exception:
            pass


def _main():
    import sys
    args = sys.argv[1:]
    push = "--push" in args
    assets = [a for a in args if not a.startswith("--")] or OTC_MAJORS
    asyncio.run(_run(assets, push=push))


if __name__ == "__main__":
    _main()
