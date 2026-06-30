"""
validation/timestamp_guard.py
=============================
Guardia de sincronía de reloj (Regla de defensa activa).

Su única responsabilidad (SRP) es decidir si una señal puede emitirse según la
diferencia (deriva) entre el reloj del SERVIDOR DEL BRÓKER y el reloj del
SISTEMA local. No sabe nada de indicadores, WebSocket ni Telegram.

------------------------------------------------------------------------------
EL "PORQUÉ" DE LA REGLA DE LOS 500 ms
------------------------------------------------------------------------------
En un entorno OTC "hostil", el feed lo genera el bróker. Si el timestamp del
bróker se aleja mucho del reloj local, puede significar:
  - datos OBSOLETOS (lag de red, buffering) -> operaríamos sobre el pasado;
  - feed DESINCRONIZADO o manipulado -> no es fiable.

En opciones binarias, donde una señal vale por unos segundos, operar con datos
desincronizados es peligroso. Por eso la regla es CONSERVADORA:

        deriva = |reloj_sistema_ms - timestamp_broker_ms|
        permitir señal  <=>  deriva <= max_drift_ms   (por defecto 500 ms)

Es decir, si la deriva SUPERA 500 ms, se DESCARTA la señal. Preferimos perder
una operación dudosa antes que ejecutar sobre información poco fiable.

Nota de diseño (SOLID): el "ahora" del sistema se inyecta como función
(`now_ms_provider`). Así la lógica es PURA y TESTEABLE sin depender del reloj
real ni de variables globales mutables.
"""

import time


def _default_now_ms():
    """Reloj del sistema en milisegundos desde época (epoch)."""
    return time.time() * 1000.0


class TimestampGuard:
    """
    Valida la sincronía bróker<->sistema antes de permitir una señal.

    Parámetros
    ----------
    max_drift_ms : float (>0) -> deriva máxima tolerada en milisegundos.
    now_ms_provider : callable -> función que devuelve el "ahora" del sistema en
                                  ms. Inyectable para pruebas deterministas.
    """

    def __init__(self, max_drift_ms=500.0, now_ms_provider=_default_now_ms):
        if max_drift_ms <= 0:
            raise ValueError("max_drift_ms debe ser > 0")
        self.max_drift_ms = float(max_drift_ms)
        self._now_ms = now_ms_provider

    def drift_ms(self, broker_ts_ms):
        """
        Deriva absoluta (ms) entre el reloj del sistema y el timestamp del
        bróker. Valor absoluto porque importa la magnitud del desfase, no si el
        bróker va por delante o por detrás.
        """
        return abs(self._now_ms() - float(broker_ts_ms))

    def is_allowed(self, broker_ts_ms):
        """
        True si la señal puede emitirse (deriva DENTRO del umbral).
        La comparación es '<=': exactamente 500 ms se considera aún válido;
        solo se descarta cuando la deriva SUPERA el umbral.
        """
        return self.drift_ms(broker_ts_ms) <= self.max_drift_ms

    def check(self, broker_ts_ms):
        """
        Devuelve una tupla (permitido: bool, deriva_ms: float) para que el
        llamador pueda registrar/loggear la deriva además de la decisión.
        """
        d = self.drift_ms(broker_ts_ms)
        return (d <= self.max_drift_ms, d)
