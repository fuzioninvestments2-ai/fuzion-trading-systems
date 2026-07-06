"""
bot/manipulation.py
===================
Guardián ANTI-MANIPULACIÓN.

No adivina la fórmula secreta de Pocket Option (imposible). Lo que hace es
DETECTAR cuándo el mercado se comporta de forma anómala/"tramposa" y avisar para
NO OPERAR ahí. Es la "barrera" honesta y útil.

Señales de alerta que detecta (sobre los precios recientes):
  1. SPIKE: un salto de precio brutal comparado con el movimiento normal
     (típico de una vela "gigante" fabricada para barrer stops/entradas).
  2. CONGELADO: el precio deja de moverse (feed estancado / mercado muerto).
  3. ESTALLIDO DE VOLATILIDAD: la agitación se dispara de golpe (mercado
     "nervioso" o manipulado) -> peligroso para entrar.

SRP: solo detecta anomalías. No opera ni conecta a red. Se prueba sin internet.
"""

import numpy as np


class ManipulationGuard:
    def __init__(self, spike_factor=8.0, freeze_ratio=0.4,
                 vol_burst_factor=3.0, min_points=30):
        self.spike_factor = spike_factor        # cuántas veces el movimiento normal
        self.freeze_ratio = freeze_ratio         # fracción de ticks sin cambio
        self.vol_burst_factor = vol_burst_factor
        self.min_points = min_points

    def check(self, prices):
        """
        prices: lista/array de precios recientes (más antiguo -> reciente).
        Devuelve {"suspicious": bool, "reasons": [textos]}.
        """
        prices = np.asarray(prices, dtype=np.float64)
        n = prices.size
        if n < self.min_points:
            return {"suspicious": False, "reasons": []}

        rets = np.diff(prices)
        abs_r = np.abs(rets)
        reasons = []

        # 1. SPIKE de MANIPULACIÓN: un salto GRANDE que REBOTA enseguida (wick que
        #    sube y vuelve, o baja y vuelve). PORQUÉ: un movimiento DIRECCIONAL real
        #    (una vela fuerte a favor de la tendencia) también da un salto grande, y
        #    ese SÍ se opera — no es manipulación. Solo es sospechoso si el salto se
        #    REVIERTE de golpe (el precio no se queda: es un pico fabricado). Antes
        #    marcaba cualquier salto grande y bloqueaba entradas válidas en OTC.
        nz = abs_r[abs_r > 0]
        med = np.median(nz) if nz.size else 0.0
        if med > 0:
            i = int(np.argmax(abs_r))
            if abs_r[i] > self.spike_factor * med and i + 1 < rets.size:
                revierte = (np.sign(rets[i + 1]) != np.sign(rets[i])
                            and abs_r[i + 1] > 0.5 * abs_r[i])
                if revierte:
                    reasons.append("spike de precio anormal")

        # 2. CONGELADO: demasiados ticks sin cambio.
        if np.mean(abs_r == 0) > self.freeze_ratio:
            reasons.append("precio congelado/estancado")

        # 3. ESTALLIDO DE VOLATILIDAD: la agitación reciente se dispara.
        if n >= 60:
            recent = rets[-20:]
            base = rets[:-20]
            if base.std() > 0 and recent.std() > self.vol_burst_factor * base.std():
                reasons.append("estallido de volatilidad")

        # 4. INESTABILIDAD: demasiados cambios de dirección seguidos (mercado
        #    errático que sube y baja sin rumbo -> peligroso para entrar).
        if n >= 40:
            signos = np.sign(rets)
            signos = signos[signos != 0]
            if signos.size >= 20:
                reversals = float(np.mean(signos[1:] != signos[:-1]))
                if reversals > 0.62:
                    reasons.append("movimiento inestable (errático)")

        return {"suspicious": len(reasons) > 0, "reasons": reasons}
