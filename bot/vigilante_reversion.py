"""
bot/vigilante_reversion.py
==========================
Núcleo del robot en vivo (sin red): mantiene las velas M1 recientes por par y, cuando
CIERRA una vela nueva, corre el escáner de reversión. Si hay señal con ventaja, la
entrega (una sola vez por vela) para que el lanzador la empuje a Telegram.

Separado de la conexión a propósito (SRP): aquí vive la lógica que SÍ se puede probar
sin internet; el lanzador `robot_reversion` solo alimenta velas y envía el texto.

Reglas:
  - Una señal por vela (dedup por timestamp de vela): no spamea con la misma.
  - Respeta el horario de mercado (`is_open`): con el mercado cerrado, calla.
  - Buffer acotado por par (no crece sin límite).
"""
from bot.escaner_reversion import senal, tarjeta


class VigilanteReversion:
    def __init__(self, pares, tabla=None, expiry_min=3, is_open=None, max_buffer=50):
        """
        pares      : lista de pares a vigilar (p.ej. ['EURCHF', 'AUDNZD', ...]).
        tabla      : tabla de reversión por par (reversion_tabla.json) o None (global).
        expiry_min : minutos de la opción sugerida.
        is_open    : callable(par)->bool para el horario; None = siempre abierto.
        max_buffer : cuántos cierres M1 recientes se guardan por par.
        """
        self.pares = list(pares)
        self.tabla = tabla
        self.expiry_min = int(expiry_min)
        self.is_open = is_open
        self.max_buffer = int(max_buffer)
        self._buffers = {p: [] for p in self.pares}
        self._ultimo_ts = {}          # par -> ts de la última vela procesada (dedup)

    def registrar(self, par, close, ts=None):
        """Registra el cierre de una vela M1 YA CERRADA en el buffer del par. Devuelve
        True si hay que evaluar señales (vela nueva y mercado abierto), False si no."""
        if par not in self._buffers:
            return False
        if ts is not None and self._ultimo_ts.get(par) == ts:
            return False              # ya procesamos esta vela: no repetir
        self._ultimo_ts[par] = ts
        buf = self._buffers[par]
        buf.append(float(close))
        if len(buf) > self.max_buffer:
            del buf[0]
        if self.is_open is not None and not self.is_open(par):
            return False              # mercado cerrado para este par: callar
        return True

    def senal_para(self, par, expiry):
        """Evalúa la reversión del buffer actual del par a un vencimiento dado. Devuelve
        la señal (dict) si hay que operar, o None. No arma la tarjeta (la arma quien la
        envía, ya con pago/hora/sesión)."""
        buf = self._buffers.get(par)
        if not buf:
            return None
        s = senal(buf, par, expiry, self.tabla)
        return s if s.get("operar") else None

    def nueva_vela(self, par, close, ts=None):
        """Compat: registra la vela y devuelve UNA señal al vencimiento por defecto
        (con tarjeta). Para varios tiempos, usa registrar()+senal_para()."""
        if not self.registrar(par, close, ts):
            return None
        s = self.senal_para(par, self.expiry_min)
        if s:
            s["tarjeta"] = tarjeta(s)
        return s

    def precargar(self, par, closes):
        """Rellena el buffer de un par con cierres M1 históricos (al arrancar), para
        tener contexto inmediato sin esperar a que lleguen velas en vivo."""
        if par not in self._buffers:
            return
        seq = [float(c) for c in closes][-self.max_buffer:]
        self._buffers[par] = seq


if __name__ == "__main__":
    # Demostración sin red: dos velas planas y luego un pico -> señal.
    v = VigilanteReversion(["EURCHF"])
    for c in (1.0800, 1.0800, 1.0800):
        v.nueva_vela("EURCHF", c)
    s = v.nueva_vela("EURCHF", 1.0810)          # subió 10 pips -> PUT
    print(s["tarjeta"] if s else "sin señal")
