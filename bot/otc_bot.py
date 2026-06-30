"""
bot/otc_bot.py
==============
Orquestador del bot OTC en MODO SIMULADO (seguro).

Coordina las piezas YA validadas del proyecto:
    feed de precios -> estrategia de confluencia -> guardia de timestamp -> log

SEGURIDAD: en modo simulado NO se conecta a ningún bróker ni se envía ninguna
orden. Las señales solo se registran. Es el banco de pruebas para ver el sistema
completo funcionando sin riesgo (coherente con la regla del proyecto:
"paper trading SIEMPRE primero").

Diseño (Reglas del proyecto):
  - Regla 1 (Modular): este módulo SOLO coordina. No recalcula indicadores ni
    reimplementa el WebSocket: reutiliza lo que ya existe (no duplicar).
  - Regla 3: manejo de excepciones por tick y global (Catch-All) + logging a
    archivo, para que un error puntual no tumbe el bot (objetivo 24/7).
  - SOLID: las dependencias (estrategia, guardia, logger) se INYECTAN. Así el
    mismo orquestador sirve para datos simulados hoy y para el cliente real de
    Pocket Option mañana, sin cambiar su código (principio abierto/cerrado).
"""

import logging
import os

from strategy.confluence import CALL, PUT, NONE


def setup_logger(name="otc_bot", log_path="logs/otc_bot.log"):
    """
    Logger Catch-All a archivo. Crea la carpeta `logs/` si no existe para no
    fallar en el primer arranque. Aislado aquí para no depender de la config de
    logging de otros módulos.
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:        # evita handlers duplicados si se reinstancia
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
    return logger


class OTCSignalBot:
    """
    Bot de señales OTC. SRP: solo COORDINA el flujo, no implementa indicadores
    ni red. Recibe sus colaboradores por inyección de dependencias.

    Parámetros
    ----------
    strategy : objeto con método update(price) -> "CALL"/"PUT"/"NONE"
               (p. ej. strategy.confluence.ConfluenceStrategy).
    guard    : objeto con método check(broker_ts_ms) -> (permitido, deriva_ms)
               (p. ej. validation.timestamp_guard.TimestampGuard).
    logger   : logger ya configurado (ver setup_logger).
    simulated: True -> nunca se envían órdenes (solo se registran). Por defecto
               True por seguridad.
    """

    def __init__(self, strategy, guard, logger, simulated=True):
        self.strategy = strategy
        self.guard = guard
        self.log = logger
        self.simulated = simulated
        # Estadísticas para inspeccionar el comportamiento sin operar de verdad.
        self.stats = {
            "ticks": 0,
            "calls": 0,
            "puts": 0,
            "descartadas_por_deriva": 0,
            "emitidas": 0,
        }

    def on_tick(self, price, broker_ts_ms):
        """
        Procesa un tick (precio + timestamp del bróker) y devuelve la señal
        finalmente emitida (o NONE). Todo va dentro de try/except: un fallo en
        un tick NO debe detener el bot (Catch-All a nivel de tick).
        """
        try:
            self.stats["ticks"] += 1

            # 1) La estrategia decide con cada precio.
            signal = self.strategy.update(price)
            if signal == NONE:
                return NONE

            # 2) El guardia valida la sincronía de reloj ANTES de emitir.
            #    El porqué: en OTC, una deriva alta implica datos poco fiables;
            #    es más seguro descartar la señal que operar a ciegas.
            allowed, drift = self.guard.check(broker_ts_ms)
            if not allowed:
                self.stats["descartadas_por_deriva"] += 1
                self.log.warning(
                    "Señal %s DESCARTADA por deriva %.0f ms (> umbral)",
                    signal, drift)
                return NONE

            # 3) Señal válida. En modo simulado NO se envía orden: se registra.
            self.stats["emitidas"] += 1
            if signal == CALL:
                self.stats["calls"] += 1
            elif signal == PUT:
                self.stats["puts"] += 1

            modo = "SIMULADA (no se envía orden)" if self.simulated else "REAL"
            self.log.info("Señal %s %s | precio=%.5f deriva=%.0f ms",
                          signal, modo, price, drift)
            return signal

        except Exception:
            # Catch-All: registramos y seguimos vivos.
            self.log.exception("Error procesando un tick (ignorado; bot sigue)")
            return NONE

    def run(self, feed):
        """
        Bucle principal sobre un `feed` iterable de (precio, broker_ts_ms), con
        Catch-All global. Devuelve las estadísticas al terminar.
        """
        self.log.info("Bot OTC iniciado (simulado=%s).", self.simulated)
        try:
            for price, broker_ts in feed:
                self.on_tick(price, broker_ts)
        except Exception:
            self.log.exception("Error fatal en el bucle principal")
        finally:
            self.log.info("Bot detenido. Resumen: %s", self.stats)
        return self.stats
