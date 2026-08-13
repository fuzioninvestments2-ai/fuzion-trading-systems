"""
core/multi_timeframe.py (fuzion_fx)
===================================
LA FOTO COMPLETA: convergencia multi-temporalidad. En vez de mirar UNA sola
temporalidad (lo que hacian los 4 bots), un PANEL de analistas — uno por
temporalidad (5s … 1D) — vota direccion y el veredicto SOLO es fuerte cuando
varias temporalidades COINCIDEN (el tiempo corto para la entrada, el largo para
la tendencia). Si se contradicen, NO operar (mercado no claro).

Es la traduccion, dentro de fuzion_fx, del motor `bot/deep_analysis.py` del
Quantum Core (misma idea de confluencia + pesos por grupo), reusando el voto de
indicadores de `core.signal_engine` (no se duplica el calculo: Regla 1).

Pesos por grupo (del planteo del usuario / skill 13): corto 15%, medio 50%,
largo 35%. El medio (donde se opera) manda; el largo confirma tendencia; el corto
afina la entrada.

HONESTIDAD: no adivina la formula de Pocket Option. Es DISCIPLINA: operar solo con
confluencia real de tiempos y callar cuando no. No garantiza acierto. Sin red.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.signal_engine import SignalEngine, CALL, PUT, NEUTRAL
from core import candle_patterns

# Temporalidades (segundos) que pide el usuario, agrupadas. La clave es SEGUNDOS
# para casar con el colector (tf en segundos).
TF_SEGUNDOS = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1D": 86400,
}

# (nombre_grupo, [tf_seg...], peso). Suma de pesos = 1.0.
GRUPOS: List = [
    ("corto", [5, 10, 15, 30], 0.15),          # afina la entrada
    ("medio", [60, 120, 180, 300], 0.50),      # donde se opera (manda)
    ("largo", [600, 900, 1800, 3600, 14400, 86400], 0.35),  # tendencia de fondo
]

# Minimo de velas para que una temporalidad opine (los indicadores necesitan
# historia; con menos, esa tf no vota en vez de dar ruido).
MIN_VELAS = 30


class MultiTimeframeAnalyzer:
    """
    Convergencia sobre varias temporalidades. `analizar` recibe las velas ya
    leidas por temporalidad y devuelve el veredicto del conjunto.
    """

    def __init__(self, indicators_cfg: Dict[str, Any],
                 umbral_convergencia: float = 0.35) -> None:
        # Reusa el motor de votos por indicador (ema, rsi, macd, bollinger).
        self.engine = SignalEngine(indicators_cfg, {"min_confirmations": 1})
        # Umbral del score |neto| (0..1) para dar señal. 0.35 => hace falta que el
        # grupo medio (0.50) mande, o medio+corto/largo alineados.
        self.umbral = float(umbral_convergencia)

    # --------------------------------------------------- direccion por tf
    def _lean_de_tf(self, candles: Optional[Dict[str, Sequence[float]]]
                    ) -> int:
        """
        Direccion NETA de una temporalidad: +1 (alcista), -1 (bajista), 0 (sin
        opinion). Es la mayoria de los 4 votos de indicadores en esa tf. Con pocas
        velas, 0 (no opina).
        """
        if not candles:
            return 0
        close = list(candles.get("close", []))
        if len(close) < MIN_VELAS:
            return 0
        votos = self.engine._votos(candles)      # {ema, rsi, macd, bollinger}
        neto = sum(1 if v > 0 else (-1 if v < 0 else 0) for v in votos.values())
        # PATRON DE VELA como votante extra (la FORMA de la vela, no solo el
        # promedio): martillo/envolvente/marubozu suman ±1; el doji (indecision)
        # no vota. Es la "historia de las velas japonesas" dentro de la formula.
        try:
            neto += candle_patterns.detectar(candles)["lean"]
        except Exception:
            pass
        return 1 if neto > 0 else (-1 if neto < 0 else 0)

    # --------------------------------------------------- veredicto del conjunto
    def analizar(self, velas_por_tf: Dict[int, Dict[str, Sequence[float]]]
                 ) -> Dict[str, Any]:
        """
        `velas_por_tf`: {tf_segundos: {open,high,low,close}}. Devuelve:
          {signal, score, convergencia, alineadas, total, por_tf, detalle}
        - score: neto ponderado en [-1, 1] (positivo=CALL, negativo=PUT).
        - convergencia: |score| (0..1), la fuerza del acuerdo.
        - alineadas/total: cuantas temporalidades DISPONIBLES coinciden con el neto.
        El peso de cada grupo se REPARTE entre las tf de ese grupo que tienen datos
        (asi el resultado no depende de cuantas tf esten disponibles).
        """
        por_tf: Dict[int, int] = {}
        score = 0.0
        detalle: List[str] = []
        for nombre, tfs, peso in GRUPOS:
            disponibles = [(tf, self._lean_de_tf(velas_por_tf.get(tf)))
                           for tf in tfs if velas_por_tf.get(tf) is not None]
            con_dato = [(tf, lean) for tf, lean in disponibles
                        if len(velas_por_tf[tf].get("close", [])) >= MIN_VELAS]
            if not con_dato:
                continue
            w = peso / len(con_dato)              # reparte el peso del grupo
            for tf, lean in con_dato:
                por_tf[tf] = lean
                score += w * lean
                if lean != 0:
                    detalle.append(f"{_nombre_tf(tf)}:{'↑' if lean > 0 else '↓'}")

        score = max(-1.0, min(1.0, score))
        convergencia = abs(score)
        neto_dir = 1 if score > 0 else (-1 if score < 0 else 0)
        votantes = [lean for lean in por_tf.values() if lean != 0]
        alineadas = sum(1 for lean in votantes if lean == neto_dir)
        total = len(votantes)

        if convergencia >= self.umbral and neto_dir != 0:
            signal = CALL if neto_dir > 0 else PUT
        else:
            signal = NEUTRAL

        return {
            "signal": signal,
            "score": round(score, 3),
            "convergencia": round(convergencia, 3),
            "alineadas": alineadas,
            "total": total,
            "por_tf": por_tf,
            "detalle": ", ".join(detalle),
        }


def _nombre_tf(seg: int) -> str:
    """Segundos -> nombre corto ('300' -> '5m'). Para el detalle legible."""
    for nombre, s in TF_SEGUNDOS.items():
        if s == seg:
            return nombre
    return f"{seg}s"
