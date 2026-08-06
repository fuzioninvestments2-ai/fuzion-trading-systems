"""
collector/po_collector.py (fuzion_fx)
=====================================
5º PROCESO: la UNICA conexion a Pocket Option. Reutiliza bot/pocket_client.py
(protocolo websocket ya probado), recibe ticks, los agrega en velas de
60/120/180/300s y las guarda en po_candles.db. Los 4 bots LEEN de ahi.

Por que un solo colector: PO permite una sola conexion por SSID. Con 4 bots como
procesos independientes, no pueden conectarse cada uno; este proceso centraliza
la conexion y comparte las velas por sqlite.

LIMITACION HONESTA: PO transmite UN activo a la vez. Para cubrir 22 pares se ROTA
(set_asset) por rondas; cada par recibe ticks durante su ventana. La cobertura es
best-effort: cuantos mas pares, mas espaciadas las velas de cada uno. El tuning
fino (tiempo por par, prioridades) se ajusta probando en vivo.

    python fuzion_fx/collector/po_collector.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

# Raiz del repo (para reutilizar bot/pocket_client.py, bot/pocket_probe.py). Se
# agrega al FINAL: el repo tiene su propio core/ (del ML) que NO debe ganar.
FUZION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(FUZION_ROOT)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)                # solo para 'bot.*'
# fuzion_fx/ va PRIMERO: 'core'/'indicators' deben resolver a los de Fuzion FX,
# no a los del proyecto ML de la raiz (que importa hmmlearn y no usamos aca).
if FUZION_ROOT in sys.path:
    sys.path.remove(FUZION_ROOT)
sys.path.insert(0, FUZION_ROOT)

from collector.aggregator import CandleAggregator          # noqa: E402
from collector.candle_store import CandleStore             # noqa: E402
from core.config import get_bot_config, ROOT               # noqa: E402

TIMEFRAMES = [60, 120, 180, 300]                            # M1, M2, M3, M5
SEGUNDOS_POR_PAR = 8                                        # ventana de escucha por par
DB_PATH = os.path.join(ROOT, "data", "db", "po_candles.db")

log = logging.getLogger("po_collector")


def _po_code(pair: str) -> str:
    """'EUR/USD' -> 'EURUSD' (codigo de activo FX real en Pocket Option)."""
    return pair.replace("/", "").upper()


def _pares() -> list:
    """Los 22 pares (iguales en los 4 bots): se toman de f1_m1."""
    return get_bot_config("f1_m1")["pairs"]


class PocketOptionCollector:
    def __init__(self, ssid: str, db_path: str = DB_PATH) -> None:
        self.store = CandleStore(db_path)
        self.agg = CandleAggregator(TIMEFRAMES)
        self.pares = _pares()
        self._code2pair = {_po_code(p): p for p in self.pares}

        # Cliente PO reutilizado (bot/pocket_client.py). demo=True: solo lectura.
        from bot.pocket_client import PocketOptionClient
        self.client = PocketOptionClient(ssid, on_tick=self._on_tick, demo=True,
                                         logger=logging.getLogger("pocket_client"))

    def _on_tick(self, asset: str, ts: int, price: float) -> None:
        """Cada precio nuevo: agrega en velas y persiste las que cierran + la viva."""
        pair = self._code2pair.get(str(asset).upper())
        if pair is None:
            return
        cerradas = self.agg.add_tick(pair, int(ts), float(price))
        for (p, tf, bucket, ohlc) in cerradas:
            self.store.upsert_candle(p, tf, bucket, ohlc["open"], ohlc["high"],
                                     ohlc["low"], ohlc["close"], ohlc["volume"])
        # Ademas, persiste la vela EN FORMACION de cada tf (precio vivo para los bots).
        for tf in TIMEFRAMES:
            cur = self.agg.current(pair, tf)
            if cur:
                bucket, o = cur
                self.store.upsert_candle(pair, tf, bucket, o["open"], o["high"],
                                         o["low"], o["close"], o["volume"])

    async def _rotar_pares(self) -> None:
        """Rota el activo escuchado por rondas (PO transmite uno a la vez)."""
        await self.client.wait_connected(timeout=30)
        while not self.client._stopped:
            for pair in self.pares:
                if self.client._stopped:
                    break
                try:
                    await self.client.set_asset(_po_code(pair), period=60)
                except Exception:
                    log.exception("No se pudo cambiar a %s", pair)
                await asyncio.sleep(SEGUNDOS_POR_PAR)

    async def run(self) -> None:
        log.info("Colector arrancado: %d pares, tf=%s, db=%s",
                 len(self.pares), TIMEFRAMES, self.store.db_path)
        # run() del cliente mantiene la conexion (reconecta solo); en paralelo
        # rotamos los pares. Ambas corren en el mismo loop (async, no hilos).
        await asyncio.gather(
            self.client.run(asset=_po_code(self.pares[0]), period=60),
            self._rotar_pares(),
        )


def _cargar_ssid() -> str:
    from bot.pocket_probe import _load_ssid
    ssid = _load_ssid("REAL")
    if not ssid:
        raise SystemExit(
            "Falta el SSID de Pocket Option. Pone POCKET_OPTION_SSID en el .env "
            "o crea ssid_real.txt con la linea 42[\"auth\",{...}] del navegador.")
    return ssid


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    collector = PocketOptionCollector(_cargar_ssid())
    try:
        asyncio.run(collector.run())
    except KeyboardInterrupt:
        collector.client.stop()
        print("\nColector detenido.")


if __name__ == "__main__":
    main()
