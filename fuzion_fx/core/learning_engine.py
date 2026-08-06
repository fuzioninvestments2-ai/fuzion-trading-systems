"""
core/learning_engine.py (fuzion_fx)
===================================
Aprendizaje por SETUP (win/loss tracking). Lee del ResultsStore el acierto real
de cada tipo de jugada (setup_id = direccion + indicadores que confirmaron) y
decide, con la config `learning`:

  - min_trades_for_setup_evaluation: muestra minima para opinar de un setup.
  - discard_setup_below_win_pct: por debajo de ese %, se DESCARTA (no emitir).
  - prioritize_setup_above_win_pct: por encima, se PRIORIZA.

PORQUE: no todos los setups rinden igual; medir el resultado REAL y silenciar los
que fallan es como el bot "aprende de cada operacion" sin tocar la logica a mano.

Sin red: solo consulta el store. Se prueba con un store en memoria.
"""

from __future__ import annotations

from typing import Any, Dict

DISCARD = "discard"
PRIORITIZE = "prioritize"
NEUTRAL = "neutral"
INSUFFICIENT = "insufficient"


class LearningEngine:
    def __init__(self, store: Any, learning_cfg: Dict[str, Any]) -> None:
        self.store = store
        self.min_trades = int(learning_cfg.get("min_trades_for_setup_evaluation", 10))
        self.discard_below = float(learning_cfg.get("discard_setup_below_win_pct", 40))
        self.prioritize_above = float(learning_cfg.get("prioritize_setup_above_win_pct", 70))

    def evaluate_setup(self, setup_id: str) -> Dict[str, Any]:
        """
        Veredicto de un setup: {verdict, win_pct, trades}. Con muestra menor a
        la minima -> 'insufficient' (aun no se juzga; se deja pasar).
        """
        st = self.store.setup_stats(setup_id)
        if st["trades"] < self.min_trades:
            return {"verdict": INSUFFICIENT, **st}
        if st["win_pct"] < self.discard_below:
            verdict = DISCARD
        elif st["win_pct"] >= self.prioritize_above:
            verdict = PRIORITIZE
        else:
            verdict = NEUTRAL
        return {"verdict": verdict, **st}

    def should_emit(self, setup_id: str) -> bool:
        """
        False solo si el setup esta DESCARTADO (rinde por debajo del umbral con
        muestra suficiente). Sin datos suficientes o neutral/priorizado -> True.
        """
        if not setup_id:
            return True
        return self.evaluate_setup(setup_id)["verdict"] != DISCARD

    def is_prioritized(self, setup_id: str) -> bool:
        """True si el setup viene rindiendo por encima del umbral alto."""
        if not setup_id:
            return False
        return self.evaluate_setup(setup_id)["verdict"] == PRIORITIZE
