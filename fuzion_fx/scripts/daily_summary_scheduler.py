"""
scripts/daily_summary_scheduler.py (fuzion_fx)
==============================================
5º PROCESO (liviano): a las 00:00 UTC-4 arma el RESUMEN DIARIO de cada bot y lo
GUARDA como resumenes/resumen_<bot_id>_YYYY-MM-DD.md y lo MANDA al Telegram de ese
bot (su token). Corre aparte de los 4 bots; no toca sus loops.

    python fuzion_fx/scripts/daily_summary_scheduler.py

Diseño testeable: la aritmetica de tiempo (proxima medianoche UTC-4, ventana del
dia cerrado) y la emision de un bot son funciones puras/inyectables; el loop solo
duerme y llama. Robusto (Regla 3): un bot que falle no tumba al resto ni al loop.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

# fuzion_fx/ al path (para core/, telegram/).
FUZION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FUZION_ROOT not in sys.path:
    sys.path.insert(0, FUZION_ROOT)

from core.config import get_bot_config, bot_ids, ROOT          # noqa: E402
from core.results_store import ResultsStore                    # noqa: E402
from core.daily_report import DailyReport                      # noqa: E402
from telegram.notifier import TelegramNotifier                 # noqa: E402

# UTC-4 fijo (la cuenta opera en ese huso; sin DST para el corte de medianoche).
TZ_UTC4 = timezone(timedelta(hours=-4))
RESUM_DIR = os.path.join(ROOT, "resumenes")

log = logging.getLogger("daily_summary")


# --------------------------------------------------------------- tiempo (puro)
def segundos_hasta_medianoche(now_epoch: float) -> float:
    """Segundos desde now hasta la PROXIMA 00:00 UTC-4."""
    ahora = datetime.fromtimestamp(now_epoch, TZ_UTC4)
    manana = (ahora + timedelta(days=1)).date()
    proxima = datetime(manana.year, manana.month, manana.day, 0, 0, 0,
                       tzinfo=TZ_UTC4)
    return proxima.timestamp() - now_epoch


def ventana_dia_cerrado(fire_epoch: float) -> Tuple[int, int, str]:
    """
    Para un disparo ~00:00 UTC-4, devuelve (inicio, fin, fecha) del dia que
    ACABA de cerrar: [ayer 00:00, hoy 00:00) UTC-4 y la fecha 'YYYY-MM-DD' de ayer.
    """
    disparo = datetime.fromtimestamp(fire_epoch, TZ_UTC4)
    fin_d = datetime(disparo.year, disparo.month, disparo.day, 0, 0, 0,
                     tzinfo=TZ_UTC4)                # medianoche recien cruzada
    inicio_d = fin_d - timedelta(days=1)
    return int(inicio_d.timestamp()), int(fin_d.timestamp()), inicio_d.date().isoformat()


# --------------------------------------------------------------- emision (inyectable)
def emitir_bot(bot_id: str, rep: DailyReport, stats: dict, fecha: str,
               out_dir: str, notifier: Optional[TelegramNotifier]) -> str:
    """Escribe el .md del bot y manda el texto corto a su Telegram. Devuelve el path."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"resumen_{bot_id}_{fecha}.md")
    with open(path, "w", encoding="utf-8") as fh:  # utf-8: el resumen lleva emojis
        fh.write(rep.to_markdown(stats, fecha))
    if notifier:
        notifier.send_text(rep.to_telegram(stats, fecha))
    else:
        log.info("[DRY-RUN sin token] resumen %s guardado en %s", bot_id, path)
    return path


def procesar_bot(bot_id: str, inicio: int, fin: int, fecha: str,
                 out_dir: str = RESUM_DIR) -> str:
    """Cablea config+store+DailyReport+notifier para un bot y emite su resumen."""
    cfg = get_bot_config(bot_id)
    store = ResultsStore(cfg["db_path"])
    try:
        rep = DailyReport(store, bot_name=cfg["name"], card_label=cfg["card_label"],
                          recovery_after=int(cfg["risk"]["recovery_after_consecutive_losses"]))
        stats = rep.build(inicio, fin)
        tg = cfg.get("telegram", {})
        token = cfg.get("telegram_token") or tg.get("bot_token")
        canal = tg.get("channel_id")
        notifier = TelegramNotifier(token, canal) if (token and canal) else None
        return emitir_bot(bot_id, rep, stats, fecha, out_dir, notifier)
    finally:
        store.close()


def run_once(fire_epoch: float, out_dir: str = RESUM_DIR) -> List[str]:
    """Genera el resumen del dia cerrado para los 4 bots. Un bot que falla no corta."""
    inicio, fin, fecha = ventana_dia_cerrado(fire_epoch)
    log.info("Resumen del dia %s (ventana %d-%d) para %d bots", fecha, inicio, fin,
             len(bot_ids()))
    paths: List[str] = []
    for bot_id in bot_ids():
        try:
            paths.append(procesar_bot(bot_id, inicio, fin, fecha, out_dir))
        except Exception:
            log.exception("Fallo el resumen de %s; sigo con el resto", bot_id)
    return paths


# --------------------------------------------------------------- loop
def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("Scheduler de resumen diario arrancado (00:00 UTC-4). Dir: %s", RESUM_DIR)
    while True:
        try:
            dormir = segundos_hasta_medianoche(time.time())
            log.info("Proximo resumen en %.0f min", dormir / 60.0)
            time.sleep(max(1.0, dormir))
            run_once(time.time())
        except KeyboardInterrupt:
            log.info("Scheduler detenido.")
            break
        except Exception:
            log.exception("Error en el ciclo del scheduler; sigo vivo")
            time.sleep(60)                          # evita bucle caliente si algo falla


if __name__ == "__main__":
    main()
