"""
bot/resilient_connector.py
==========================
Conector de reconexión REUTILIZABLE con backoff exponencial + jitter.

Su única responsabilidad (SRP) es: "intentar conectar y, si falla, reintentar
con esperas crecientes". Es GENÉRICO: no sabe de Pocket Option ni de WebSockets.
Recibe una corrutina `connect_once` (un único intento) por inyección, lo que lo
hace trivial de testear sin red real.

------------------------------------------------------------------------------
EL "PORQUÉ" DEL BACKOFF EXPONENCIAL CON EQUAL JITTER
------------------------------------------------------------------------------
Reintentar de inmediato y en bucle saturaría el servidor (justo lo que la
Regla 3 quiere evitar). El backoff hace crecer la espera tras cada fallo:

        cap   = min(max_delay, base * 2^(intento-1))
        delay = cap/2 + random(0, cap/2)      # "equal jitter"

  - exponencial: 1s, 2s, 4s, 8s... (limitado por max_delay) -> no martillea.
  - equal jitter: garantiza una espera mínima (cap/2) y reparte el resto al azar
    para evitar "estampidas" de reintentos sincronizados.

Nota de diseño (SOLID/testabilidad): tanto la función de espera (`sleep_fn`)
como el azar se pueden inyectar; en pruebas usamos un sleep que no espera de
verdad, así el test es instantáneo y determinista.
"""

import asyncio
import logging
import random


class ResilientConnector:
    """
    Envuelve un intento de conexión con reintentos y backoff.

    Parámetros
    ----------
    base_delay : float   -> espera base del backoff (segundos).
    max_delay : float    -> techo del backoff (segundos).
    max_retries : int|None -> reintentos máximos; None = infinito (24/7).
    logger : Logger|None -> para registrar eventos (opcional).
    sleep_fn : callable  -> función async de espera (inyectable para tests).
    rng : random.Random|None -> generador aleatorio (inyectable para tests).
    """

    def __init__(self, base_delay=1.0, max_delay=30.0, max_retries=None,
                 logger=None, sleep_fn=asyncio.sleep, rng=None):
        self.base_delay = float(base_delay)
        self.max_delay = float(max_delay)
        self.max_retries = max_retries
        self.log = logger or logging.getLogger("resilient_connector")
        self._sleep = sleep_fn
        self._rng = rng or random.Random()

    def backoff(self, attempt):
        """Retardo con backoff exponencial + equal jitter (ver cabecera)."""
        cap = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return cap / 2.0 + self._rng.uniform(0.0, cap / 2.0)

    async def connect(self, connect_once):
        """
        Llama a `connect_once()` (corrutina de un solo intento) y reintenta con
        backoff hasta lograrlo o agotar `max_retries`.

        Devuelve lo que devuelva `connect_once` en el primer éxito.
        Lanza ConnectionError si se agotan los reintentos.
        """
        attempt = 0
        while True:
            try:
                result = await connect_once()
                if attempt > 0:
                    self.log.info("Reconectado tras %d intento(s).", attempt)
                return result
            except asyncio.CancelledError:
                # Cancelación externa (apagado): propagar para salir limpio.
                raise
            except Exception as exc:
                attempt += 1
                if self.max_retries is not None and attempt > self.max_retries:
                    self.log.error(
                        "Reconexión fallida tras %d intentos: %s",
                        self.max_retries, exc)
                    raise ConnectionError(
                        f"No se pudo conectar tras {self.max_retries} intentos"
                    ) from exc
                delay = self.backoff(attempt)
                self.log.warning(
                    "Conexión fallida (%s: %s). Reintento #%d en %.2fs",
                    type(exc).__name__, exc, attempt, delay)
                await self._sleep(delay)
