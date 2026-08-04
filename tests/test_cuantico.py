"""
tests/test_cuantico.py
======================
TAREA 2 del manual: tests del Motor Cuantico (`bot/cuantico.py`), SIN red.

PORQUE: el motor decide OPERAR solo con >=90% de probabilidad y >=90% de
convergencia. Estos tests fijan ese contrato con datos SINTETICOS deterministas
(sin random, sin red) para que un cambio futuro que rompa el umbral se detecte.

Los 4 casos del manual:
  1. Todos los timeframes alcistas -> probabilidad > 90% y direccion CALL.
  2. Grupos desalineados -> penalizacion (menos alineados, NO opera).
  3. Umbral recovery 95%  (payout < 80% exige probabilidad >= 95%).
  4. Umbral normal 90%    (payout normal exige probabilidad >= 90%).

Valores esperados MEDIDOS del motor real (no inventados):
  - 9/9 alcista -> prob 95.3, conv 100.0
  - 8/9 alcista -> prob 90.9, conv 95.4  (usado para separar 90 vs 95)
"""

from __future__ import annotations

import os
import sys
from typing import Dict

import numpy as np
import pandas as pd

# El test corre desde cualquier CWD: se anade la raiz del proyecto al path para
# poder importar el paquete `bot` y `config` sin instalar nada.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from bot import cuantico as q          # noqa: E402
from config import settings            # noqa: E402


def _frame(trend: int, n: int = 60, base: float = 1.10,
           step: float = 0.0004) -> pd.DataFrame:
    """
    Construye OHLCV de UN timeframe con una tendencia casi monotona.

    PORQUE: una serie limpia (trend=+1 alcista, -1 bajista) hace que momentum,
    RSI, Bollinger, MACD y Estocastico voten todos en la misma direccion, con
    fuerza alta y estable -> senal deterministica, ideal para asertar umbrales.
    """
    idx = np.arange(n)
    close = base + trend * step * idx
    op = close - trend * step * 0.5
    high = np.maximum(op, close) + step * 0.2
    low = np.minimum(op, close) - step * 0.2
    volume = np.full(n, 1000.0)
    return pd.DataFrame({"open": op, "high": high, "low": low,
                         "close": close, "volume": volume})


def _frames_alineados(trend: int) -> Dict[int, pd.DataFrame]:
    """Los 9 timeframes con la MISMA tendencia (todos CALL o todos PUT)."""
    return {tf: _frame(trend) for tf in q.TIMEFRAMES_9}


def _frames_8_de_9() -> Dict[int, pd.DataFrame]:
    """8 alcistas y 1 bajista -> prob ~90.9 (borde entre 90 y 95)."""
    ultimo = q.TIMEFRAMES_9[-1]
    return {tf: _frame(-1 if tf == ultimo else +1) for tf in q.TIMEFRAMES_9}


def test_todos_call_probabilidad_mayor_90() -> None:
    """Caso 1: 9/9 alcistas -> probabilidad > 90% y direccion CALL."""
    r = q.calculate_quantum_probability(_frames_alineados(+1))
    assert r["direccion"] == "CALL", r["direccion"]
    assert r["alineados"] == 9, r["alineados"]
    assert r["probabilidad"] > 90.0, r["probabilidad"]
    # Con 9/9 la convergencia logaritmica es 100% (ln(10)/ln(10)).
    assert q.calculate_logarithmic_convergence(r["alineados"]) == 100.0
    # Y el gate final debe dar OPERAR (payout normal, hora valida).
    dec = q.validate_signal_90(_frames_alineados(+1), payout=92, hora_utc=14)
    assert dec["operar"] is True, dec["motivo"]


def test_grupos_desalineados_penaliza() -> None:
    """Caso 2: timeframes mezclados -> menos alineados y NO opera."""
    mix = {tf: _frame(+1 if i % 2 == 0 else -1)
           for i, tf in enumerate(q.TIMEFRAMES_9)}
    r = q.calculate_quantum_probability(mix)
    alineado_total = q.calculate_quantum_probability(_frames_alineados(+1))
    # Penalizacion: menos tiempos coincidentes y menor probabilidad que 9/9.
    assert r["alineados"] < alineado_total["alineados"], r["alineados"]
    assert r["probabilidad"] < alineado_total["probabilidad"]
    dec = q.validate_signal_90(mix, payout=92, hora_utc=14)
    assert dec["operar"] is False, dec["motivo"]
    assert "contradictorios" in dec["motivo"], dec["motivo"]


def test_umbral_recovery_95() -> None:
    """Caso 3: payout < 80% exige probabilidad >= 95% (recovery)."""
    frames = _frames_8_de_9()
    prob = q.calculate_quantum_probability(frames)["probabilidad"]
    # La prob de 8/9 cae entre 90 y 95: bloquea en recovery pero pasa en normal.
    assert 90.0 <= prob < 95.0, prob
    dec = q.validate_signal_90(frames, payout=70, hora_utc=14)   # payout bajo
    assert dec["operar"] is False, dec["motivo"]
    assert "95%" in dec["motivo"], dec["motivo"]
    # El umbral duro coincide con la constante del motor.
    assert q.PROB_MIN_PAYOUT_BAJO == 95.0


def test_umbral_normal_90() -> None:
    """Caso 4: payout normal exige probabilidad >= 90% (misma senal 8/9 opera)."""
    frames = _frames_8_de_9()
    dec = q.validate_signal_90(frames, payout=92, hora_utc=14)    # payout normal
    assert dec["operar"] is True, dec["motivo"]
    # El umbral normal coincide entre el motor y la config centralizada (TAREA 1).
    assert q.PROB_MIN == 90.0
    assert settings.PROB_MIN == q.PROB_MIN
    assert settings.CONV_MIN == q.CONV_MIN


def _run_all() -> None:
    """Corre los tests como script (sin pytest) y reporta OK/fallo."""
    tests = [test_todos_call_probabilidad_mayor_90,
             test_grupos_desalineados_penaliza,
             test_umbral_recovery_95,
             test_umbral_normal_90]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
