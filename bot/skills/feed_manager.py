"""
bot/skills/feed_manager.py
==========================
Gestor de FEED con REDUNDANCIA (solo lectura). Mantiene el análisis vivo aunque una
fuente se caiga:
  - PRINCIPAL: Pocket Option (SSID) — es el precio en el que operas.
  - RESPALDO:  Dukascopy — cubre cuando PO desconecta el mercado real (~16:30-20:00).

Lógica de salud/failover: si no llegan ticks de PO por más de `silencio_seg`, se
declara la fuente PRINCIPAL en silencio y se activa el RESPALDO. Cuando PO vuelve a
enviar ticks, se regresa a PRINCIPAL. El reloj es inyectable (`now_ms`) para poder
testear sin red ni depender de la hora del sistema.

Este módulo NO coloca órdenes ni descarga por su cuenta: decide qué fuente está
activa y expone la salud; el loop de arranque hace el polling del respaldo.
"""
POCKET = "pocket"
DUKASCOPY = "dukascopy"
SILENCIO_SEG = 90                     # sin ticks de PO por más de esto → respaldo


class FeedManager:
    def __init__(self, silencio_seg=SILENCIO_SEG):
        self.silencio_seg = silencio_seg
        self._ultimo_pocket_ms = None
        self._fuente = POCKET
        self.cambios = 0              # nº de veces que cambió de fuente (para auditar)

    def registrar_tick_pocket(self, ts_ms):
        """Llamar en cada tick de Pocket Option (marca la fuente principal viva)."""
        self._ultimo_pocket_ms = int(ts_ms)

    def revisar(self, now_ms):
        """
        Decide la fuente activa según la salud de PO. Devuelve POCKET o DUKASCOPY.
        Cambia a respaldo si PO lleva > silencio_seg sin ticks; vuelve a PO si hay
        tick reciente.
        """
        principal_viva = (self._ultimo_pocket_ms is not None and
                          (now_ms - self._ultimo_pocket_ms) <= self.silencio_seg * 1000)
        nueva = POCKET if principal_viva else DUKASCOPY
        if nueva != self._fuente:
            self._fuente = nueva
            self.cambios += 1
        return self._fuente

    @property
    def fuente(self):
        return self._fuente

    def estado(self, now_ms):
        """Resumen para el dashboard/logs."""
        gap = None
        if self._ultimo_pocket_ms is not None:
            gap = round((now_ms - self._ultimo_pocket_ms) / 1000, 1)
        return {"fuente_activa": self.revisar(now_ms),
                "pocket_silencio_seg": gap, "cambios_de_fuente": self.cambios}


def poll_dukascopy(par, tf_seg, minutos=5):
    """
    Trae las velas más recientes de Dukascopy para `par` (respaldo en vivo). Devuelve
    lista de dicts timestamp/open/high/low/close/volume, o [] si falla o no hay red.
    Solo se usa cuando el FeedManager activa el respaldo.
    """
    try:
        import datetime as dt

        import dukascopy_python as duka
        from bot.dukascopy_loader import instrumento_de, _a_formato

        inst = instrumento_de(par)
        if inst is None:
            return []
        fin = dt.datetime.now(dt.timezone.utc)
        ini = fin - dt.timedelta(minutes=minutos)
        df = duka.fetch(inst, duka.INTERVAL_SEC_1, duka.OFFER_SIDE_BID, ini, fin)
        if df is None or len(df) == 0:
            return []
        base = _a_formato(df)
        return base.to_dict("records")
    except Exception:
        return []                     # respaldo nunca debe tumbar el bot
