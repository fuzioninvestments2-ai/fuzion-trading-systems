"""
bot/run_demo.py
===============
Arranque del bot OTC contra la cuenta DEMO de Pocket Option.

MODO: SOLO LECTURA. Lee precios de la demo y registra señales. NUNCA envía
órdenes (no llama a place_order). Es el puente entre el cliente real y nuestro
orquestador, manteniendo la seguridad ("paper trading SIEMPRE primero").

Seguridad:
  - El SSID se lee de la variable de entorno POCKET_OPTION_SSID (archivo .env,
    que está en .gitignore). NUNCA se escribe en el código ni se versiona.
  - Se usa el endpoint DEMO del cliente (paper_trading=True por defecto).
  - Reconexión robusta vía ResilientPocketOptionClient.

Limitación honesta: el cliente Pocket Option del repo es una implementación
BÁSICA. Su `get_market_data` devuelve un precio pero NO un timestamp del bróker.
Mientras no parseemos ese timestamp del socket, el guardia de deriva no puede
comparar relojes de verdad; por eso, si no hay timestamp del bróker, usamos el
reloj del sistema y lo dejamos registrado como advertencia (no como validación
real). Esto se mejorará cuando confirmemos el formato real de los mensajes.
"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.otc_bot import OTCSignalBot, setup_logger
from strategy.confluence import ConfluenceStrategy, StrategyConfig
from validation.timestamp_guard import TimestampGuard


def _system_now_ms():
    return time.time() * 1000.0


class LiveDemoRunner:
    """
    Bucle de LECTURA en vivo: conecta -> lee precios -> alimenta el bot -> log.

    Dependencias inyectadas (SOLID), lo que permite probarlo con un cliente
    simulado (mock) sin red real:
      client : objeto tipo broker con connect()/get_market_data(symbol).
      bot    : OTCSignalBot (decide y registra señales; nunca opera en demo).
      symbol : activo a observar (p. ej. "EURUSD_otc").
    """

    def __init__(self, client, bot, symbol, *, poll_interval=1.0,
                 max_ticks=None, logger=None, now_ms_provider=_system_now_ms,
                 broker_ts_extractor=None):
        self.client = client
        self.bot = bot
        self.symbol = symbol
        self.poll_interval = float(poll_interval)
        self.max_ticks = max_ticks      # None = indefinido (24/7)
        self.log = logger or setup_logger("live_demo", "logs/live_demo.log")
        self._now_ms = now_ms_provider
        # Extrae el timestamp del bróker de un MarketData; si no hay, None.
        self._extract_ts = broker_ts_extractor or self._default_ts_extractor
        self._stopped = False
        self._warned_no_ts = False

    @staticmethod
    def _default_ts_extractor(md):
        """
        Intenta leer un timestamp del bróker desde el MarketData. El cliente
        básico no lo rellena de forma fiable, así que normalmente devolverá None.
        """
        ts = getattr(md, "timestamp", "") or ""
        if not ts:
            return None
        try:
            return float(ts)           # si algún día viene en ms numéricos
        except (TypeError, ValueError):
            return None

    def stop(self):
        self._stopped = True

    async def run(self):
        """
        Conecta (con reconexión) y entra en el bucle de lectura. SOLO LECTURA:
        en ningún punto se envían órdenes. Catch-All global para no caerse.
        """
        self.log.info("LiveDemoRunner: conectando a la DEMO (solo lectura)...")
        await self.client.connect()     # ResilientPocketOptionClient reintenta
        self.log.info("Conectado. Observando %s (sin enviar órdenes).",
                      self.symbol)

        ticks = 0
        try:
            while not self._stopped:
                if self.max_ticks is not None and ticks >= self.max_ticks:
                    break
                try:
                    md = await self.client.get_market_data(self.symbol)
                    price = float(getattr(md, "last", 0.0) or 0.0)

                    # Timestamp del bróker: si no lo hay, usamos el del sistema
                    # y avisamos UNA vez (no es una validación real de deriva).
                    broker_ts = self._extract_ts(md)
                    if broker_ts is None:
                        if not self._warned_no_ts:
                            self.log.warning(
                                "Sin timestamp del broker: el guardia de deriva "
                                "no puede comparar relojes (se usa reloj local).")
                            self._warned_no_ts = True
                        broker_ts = self._now_ms()

                    self.bot.on_tick(price, broker_ts)
                    ticks += 1
                except Exception:
                    # Un fallo leyendo un tick no debe tumbar el bucle.
                    self.log.exception("Error leyendo un tick (se continúa)")

                await asyncio.sleep(self.poll_interval)
        finally:
            self.log.info("LiveDemoRunner detenido. Resumen: %s", self.bot.stats)
        return self.bot.stats


def build_demo_runner(symbol="EURUSD_otc", poll_interval=1.0, max_ticks=None):
    """
    Arma el runner con el cliente REAL de Pocket Option (demo). Requiere
    POCKET_OPTION_SSID en el entorno. Se importa aquí dentro para que el módulo
    pueda testearse con un mock sin exigir esa dependencia/credencial.
    """
    ssid = os.getenv("POCKET_OPTION_SSID", "")
    if not ssid:
        raise RuntimeError(
            "Falta POCKET_OPTION_SSID. Crea un archivo .env con tu SSID de la "
            "cuenta DEMO (ver .env.example). NUNCA lo subas a git.")

    # Import perezoso: solo cuando de verdad vamos a conectar.
    from bot.resilient_pocket_option import ResilientPocketOptionClient

    logger = setup_logger("live_demo", "logs/live_demo.log")
    client = ResilientPocketOptionClient(
        {"paper_trading": True, "ssid": ssid},   # DEMO siempre
        base_delay=1.0, max_delay=30.0, logger=logger)
    strategy = ConfluenceStrategy(StrategyConfig())
    guard = TimestampGuard(max_drift_ms=500.0)
    bot = OTCSignalBot(strategy, guard, logger, simulated=True)  # nunca opera
    return LiveDemoRunner(client, bot, symbol, poll_interval=poll_interval,
                          max_ticks=max_ticks, logger=logger)


def main():
    # Carga .env si python-dotenv está disponible (opcional).
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass  # si no está, se usa el entorno tal cual

    runner = build_demo_runner()
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
