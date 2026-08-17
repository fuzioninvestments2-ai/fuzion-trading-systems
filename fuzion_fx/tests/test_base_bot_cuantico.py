"""
tests/test_base_bot_cuantico.py (fuzion_fx)
===========================================
Valida la integracion del MOTOR CUANTICO en base_bot (motor='cuantico'):
 - analisis_cuantico junta los 7 tiempos del feed y da un veredicto con direccion.
 - scan_once EMITE cuando el veredicto habilita (OPERAR) y NO emite en NO_OPERAR.
 - _result_desde_cuantico arma un result usable por el pipeline (direccion, prob).
SIN red (feed en memoria por tf).
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                     # noqa: E402
from bots.base_bot import BaseBot                               # noqa: E402


def _velas_tendencia(direccion, seed):
    rng = np.random.RandomState(seed)
    n = 200
    drift = np.linspace(0.0, direccion * 0.012, n)
    ru = np.cumsum(rng.normal(0, 0.0004, n))
    ru = ru - np.linspace(0.0, ru[-1], n)
    close = 1.1150 + drift + 0.5 * ru
    o = np.concatenate([[close[0]], close[:-1]])
    h = np.maximum(o, close) * 1.0003
    l = np.minimum(o, close) * 0.9997
    return {"open": list(o), "high": list(h), "low": list(l),
            "close": list(close), "volume": [0.0] * n}


class _FeedTendencia:
    """Devuelve la MISMA tendencia para todos los tf (los 7 coinciden) y pago en
    banda."""

    def __init__(self, direccion):
        self._velas = _velas_tendencia(direccion, seed=7)

    def get_candles(self, pair, tf, count=200):
        return self._velas

    def get_payout(self, pair):
        return 85.0


def _bot(direccion):
    bot = BaseBot("f1_m1", price_feed=_FeedTendencia(direccion),
                  store=ResultsStore(":memory:"))
    bot.motor = "cuantico"
    bot.signal_cooldown = 0
    bot.prefilter_seconds = 0
    bot._schedule_enabled = False
    return bot


def test_analisis_cuantico_junta_tiempos() -> None:
    bot = _bot(+1)
    qr = bot.analisis_cuantico("EUR/USD")
    assert qr is not None
    assert qr["direccion"] == 1                       # tendencia alcista -> CALL
    assert qr["veredicto"] != "NO_OPERAR"
    assert len(qr["por_tf"]) >= 3                      # varios tiempos participaron


def test_scan_emite_en_operar() -> None:
    bot = _bot(+1)
    # Forzar veredicto OPERAR (deterministico) para validar que el pipeline emite.
    bot.analisis_cuantico = lambda pair: {
        "veredicto": "OPERAR", "direccion": 1, "probabilidad": 0.93,
        "alineacion": 0.80, "n_alineados": 5,
        "por_tf": {60: {"modo": "slide", "patron": "martillo"}}}
    emitidas = bot.scan_once(now=1000.0)
    assert emitidas and emitidas[0]["direction"] == "CALL"


def test_entrada_con_anticipacion_minima() -> None:
    # La hora de entrada NUNCA debe quedar a menos de LEAD_MIN segundos de la emision
    # (si no, el card llega "fuera de hora"). Se corre a la vela siguiente.
    bot = _bot(+1)
    bot.analisis_cuantico = lambda pair: {
        "veredicto": "OPERAR", "direccion": 1, "probabilidad": 0.93,
        "alineacion": 0.80, "n_alineados": 5,
        "por_tf": {60: {"modo": "slide", "patron": None}}}
    emitidas = bot.scan_once(now=1000.0)
    assert emitidas
    r = emitidas[0]
    assert r["entry_show_ts"] - r["ts"] >= bot.LEAD_MIN     # entrada con margen real


def test_scan_no_emite_en_no_operar() -> None:
    bot = _bot(+1)
    bot.analisis_cuantico = lambda pair: {
        "veredicto": "NO_OPERAR", "direccion": 1, "probabilidad": 0.4,
        "alineacion": 0.2, "n_alineados": 1, "por_tf": {}}
    assert bot.scan_once(now=1000.0) == []


def test_result_desde_cuantico_tiene_prob_y_direccion() -> None:
    bot = _bot(-1)
    candles = _velas_tendencia(-1, seed=7)
    qr = bot.analisis_cuantico("USD/JPY")
    r = bot._result_desde_cuantico("USD/JPY", candles, qr)
    assert r["signal"] in ("CALL", "PUT")
    assert 0.0 <= r["probabilidad"] <= 1.0
    assert r["atr"] > 0 and "confirming" in r


def _run_all() -> None:
    tests = [test_analisis_cuantico_junta_tiempos, test_scan_emite_en_operar,
             test_entrada_con_anticipacion_minima,
             test_scan_no_emite_en_no_operar,
             test_result_desde_cuantico_tiene_prob_y_direccion]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
