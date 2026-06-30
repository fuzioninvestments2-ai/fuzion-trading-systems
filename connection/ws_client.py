"""
connection/ws_client.py
=======================
Cliente WebSocket ROBUSTO con reconexión automática (Regla 3).

Pensado para feeds frágiles y "hostiles" como el socket OTC de Pocket Option
(no oficial, propenso a micro-cortes). NO está acoplado a indicadores ni a
Telegram: recibe el manejador de mensajes por INYECCIÓN DE DEPENDENCIAS, de
modo que esta clase solo se ocupa de "conectar, recibir y reconectar" (SRP).

Diseño (Reglas del proyecto):
  - Regla 3 (Errores): try/except robustos + reconexión con backoff exponencial
    + logging Catch-All a archivo, para mantener el bot vivo 24/7.
  - SOLID: el on_message se inyecta; sin variables globales mutables.

------------------------------------------------------------------------------
EL "PORQUÉ" DEL BACKOFF EXPONENCIAL CON JITTER
------------------------------------------------------------------------------
Si al caerse la conexión reintentáramos de inmediato y en bucle, saturaríamos
el servidor (y nuestro propio hilo) -> es justo lo que la Regla 3 quiere evitar.

Backoff exponencial: el tiempo de espera crece como base * 2^(intento-1),
limitado por un techo `max_delay`. Así, tras varios fallos seguidos, esperamos
cada vez más (1s, 2s, 4s, 8s...) en lugar de martillear el servidor.

Jitter (aleatoriedad): si muchos clientes reconectaran exactamente al mismo
tiempo se produciría una "estampida" sincronizada. Añadimos azar para repartir
los reintentos. Usamos "equal jitter":

        cap   = min(max_delay, base * 2^(intento-1))
        delay = cap/2 + random(0, cap/2)

equal jitter garantiza un mínimo de espera (cap/2) y a la vez dispersa el resto.
Al CONECTAR con éxito, el contador de intentos se reinicia a 0.
"""

import asyncio
import logging
import random

import websockets


def _build_logger(log_file):
    """
    Crea un logger que escribe a archivo (logging Catch-All). Se aísla aquí
    para no depender de la configuración global de logging de otros módulos.
    """
    logger = logging.getLogger("ws_client")
    logger.setLevel(logging.INFO)
    # Evita duplicar handlers si se instancian varios clientes.
    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


class ReconnectingWebSocketClient:
    """
    Cliente WebSocket que se reconecta solo ante cualquier caída.

    Parámetros
    ----------
    url : str               -> URL del WebSocket (ws:// o wss://).
    on_message : callable    -> manejador inyectado; recibe cada mensaje. Puede
                                ser una función normal o una corrutina async.
    base_delay : float       -> espera base del backoff (segundos).
    max_delay : float        -> techo del backoff (segundos).
    max_retries : int|None   -> nº máximo de reintentos seguidos; None = infinito
                                (para operar 24/7).
    log_file : str           -> archivo donde se registran errores y eventos.
    """

    def __init__(self, url, on_message, *, base_delay=1.0, max_delay=30.0,
                 max_retries=None, log_file="ws_client.log"):
        self.url = url
        self.on_message = on_message
        self.base_delay = float(base_delay)
        self.max_delay = float(max_delay)
        self.max_retries = max_retries
        self.log = _build_logger(log_file)
        self._stopped = False        # bandera para una parada limpia

    def stop(self):
        """Solicita una parada ordenada del bucle de reconexión."""
        self._stopped = True

    def _backoff(self, attempt):
        """Calcula el retardo con backoff exponencial + equal jitter."""
        cap = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        # equal jitter: mitad fija + mitad aleatoria (ver cabecera del módulo).
        return cap / 2.0 + random.uniform(0.0, cap / 2.0)

    async def _dispatch(self, message):
        """Llama al handler inyectado, soportando handlers sync o async."""
        result = self.on_message(message)
        # Si el handler es una corrutina, la esperamos; si no, ya terminó.
        if asyncio.iscoroutine(result):
            await result

    async def run(self):
        """
        Bucle principal: conecta, recibe mensajes y, ante cualquier error,
        reconecta con backoff. No se cae nunca por un error puntual (Catch-All).
        """
        attempt = 0
        while not self._stopped:
            try:
                # Timeouts de ping para detectar conexiones "zombi" (el socket
                # parece vivo pero no fluye nada): clave en feeds OTC inestables.
                async with websockets.connect(
                        self.url, ping_interval=20, ping_timeout=20) as ws:
                    attempt = 0                       # éxito -> reiniciar backoff
                    self.log.info("Conectado a %s", self.url)
                    async for message in ws:
                        # Un fallo procesando UN mensaje no debe tumbar la
                        # conexión: lo aislamos con su propio try/except.
                        try:
                            await self._dispatch(message)
                        except Exception:
                            self.log.exception(
                                "Error en on_message (mensaje ignorado)")

            except asyncio.CancelledError:
                # Cancelación externa (p. ej. apagado): propagar para salir.
                self.log.info("Cliente cancelado; saliendo.")
                raise

            except Exception as exc:
                # Catch-All: cualquier error de red/protocolo se registra y se
                # reintenta. El bot sigue vivo.
                if self._stopped:
                    break
                attempt += 1
                if self.max_retries is not None and attempt > self.max_retries:
                    self.log.error(
                        "Máximo de reintentos (%s) alcanzado. Abortando.",
                        self.max_retries)
                    break
                delay = self._backoff(attempt)
                self.log.warning(
                    "Desconexión (%s: %s). Reintento #%d en %.2fs",
                    type(exc).__name__, exc, attempt, delay)
                await asyncio.sleep(delay)

        self.log.info("Bucle de conexión finalizado.")
