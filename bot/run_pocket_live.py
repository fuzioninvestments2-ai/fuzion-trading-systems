"""
bot/run_pocket_live.py
======================
Bot EN VIVO con precios REALES de Pocket Option (demo, solo lectura).

Hace de punta a punta:
  precios reales de PO -> velas -> historial (SQLite) -> estrategia -> señal

NO envía órdenes. Es la integración real funcionando para que la VEAS.

Uso:
  1. Ten tu SSID en ssid.txt (línea 42["auth",{...}] del navegador, cuenta DEMO).
  2. python3 bot/run_pocket_live.py
  (Se detiene con Ctrl+C.)
"""

import asyncio
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.pocket_client import PocketOptionClient
from bot.candles import CandleBuilder
from bot.history import HistoryRepository
from bot.scoring_strategy import ScoringStrategy, CALL, PUT
from bot.config import TradingConfig
from bot.pocket_probe import _load_ssid

ASSET = "EURUSD_otc"      # activo a escuchar (código de Pocket Option)
PERIOD = 60               # velas de 1 minuto (M1)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s")
    log = logging.getLogger("live")

    ssid = _load_ssid()
    if not ssid:
        raise RuntimeError("Falta ssid.txt con tu 42[\"auth\",{...}] de la demo.")

    # Piezas del motor.
    cb = CandleBuilder(PERIOD)
    repo = HistoryRepository(os.path.join(ROOT, "history.db"))
    cfg = TradingConfig(stack_method="aggressive")
    cfg.min_confidence = 0.25         # más sensible para ver señales en vivo
    strat = ScoringStrategy(cfg)

    contador = {"ticks": 0}

    def analizar_y_guardar(closed_candle):
        """Guarda la vela cerrada y analiza la serie reciente."""
        repo.record_candle(ASSET, "M1", closed_candle)
        df = cb.to_dataframe()
        if len(df) < 5:                # con muy pocas velas no hay nada que medir
            return
        signal, conf, d = strat.analyze(df)
        flecha = {"CALL": "⬆️ UP", "PUT": "⬇️ DOWN"}.get(signal, "⏸️ sin señal")
        log.info("── VELA CERRADA %s | %s | confianza=%.0f%% | velas=%d "
                 "(guardadas en history.db)", ASSET, flecha, conf * 100, len(df))

    def on_tick(asset, ts, price):
        # ts viene en SEGUNDOS -> el constructor de velas usa milisegundos.
        contador["ticks"] += 1
        # Mostramos el precio en vivo cada 25 ticks (para ver actividad ya).
        if contador["ticks"] % 25 == 0:
            log.info("precio %s = %s", asset, price)
        closed = cb.add_tick(price, ts * 1000.0)
        if closed is not None:
            analizar_y_guardar(closed)

    def on_history(payload):
        # Sembramos velas con el historial que envía PO al conectar.
        hist = payload.get("history", []) if isinstance(payload, dict) else []
        for row in hist:
            try:
                t, p = float(row[0]), float(row[1])
            except (IndexError, TypeError, ValueError):
                continue
            cb.add_tick(p, t * 1000.0)
        log.info("Historial recibido: %d puntos -> %d velas formadas",
                 len(hist), len(cb.closed_candles()))

    def on_balance(payload):
        if isinstance(payload, dict):
            log.info("Balance %s: $%.2f",
                     "DEMO" if payload.get("isDemo") else "REAL",
                     float(payload.get("balance", 0)))

    client = PocketOptionClient(ssid, on_tick=on_tick, on_history=on_history,
                                on_balance=on_balance, demo=True, logger=log)

    print(f"Escuchando {ASSET} en vivo (demo, solo lectura). Ctrl+C para parar.")
    try:
        asyncio.run(client.run(asset=ASSET, period=PERIOD))
    except KeyboardInterrupt:
        print("\nDetenido. Velas guardadas en history.db")


if __name__ == "__main__":
    main()
