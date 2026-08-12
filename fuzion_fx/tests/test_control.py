"""
tests/test_control.py (fuzion_fx)
=================================
Valida el control de PAUSA: el estado en archivo, que el bot NO emite en pausa, y
el router de acciones del servidor (pausar/reanudar). SIN red.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import control                                        # noqa: E402
from core.results_store import ResultsStore                     # noqa: E402
from core.signal_engine import CALL                             # noqa: E402
from data.price_feed import InMemoryPriceFeed                   # noqa: E402
from bots.base_bot import BaseBot                               # noqa: E402


class _FakeEngine:
    def __init__(self): self.n = 0
    def analyze(self, candles):
        self.n += 1
        if self.n <= 2:
            return {"signal": CALL, "confirmations": 3, "votes": {},
                    "confirming": ["ema", "macd", "rsi"], "setup_id": "s",
                    "atr": 0.001, "price": 1.10, "readings": {"rsi": 25.0}}
        return {"signal": "NEUTRAL", "confirmations": 0, "votes": {},
                "confirming": [], "setup_id": None, "atr": 0.0, "price": 1.10,
                "readings": {"rsi": 50.0}}


def test_control_archivo() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    try:
        assert control.esta_pausado(tmp.name) is False        # default
        control.set_pausado(True, tmp.name)
        assert control.esta_pausado(tmp.name) is True
        control.set_pausado(False, tmp.name)
        assert control.esta_pausado(tmp.name) is False
    finally:
        os.unlink(tmp.name)


def test_bot_no_emite_en_pausa() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    _orig = control.CONTROL_PATH
    control.CONTROL_PATH = tmp.name                            # apunta el control al temp
    try:
        feed = InMemoryPriceFeed()
        feed.set_candles("AUD/CAD", {k: list(np.linspace(1.10, 1.11, 60))
                                     for k in ("open", "high", "low", "close")})
        bot = BaseBot("f1_m1", price_feed=feed, store=ResultsStore(":memory:"))
        bot.pairs = ["AUD/CAD"]; bot.prefilter_seconds = 0; bot._schedule_enabled = False
        bot.engine = _FakeEngine()
        control.set_pausado(True, tmp.name)
        assert bot.scan_once(now=1000.0) == []                 # pausado -> no emite
        control.set_pausado(False, tmp.name)
        bot.engine = _FakeEngine()
        assert len(bot.scan_once(now=1000.0)) == 1             # reanudado -> emite
    finally:
        control.CONTROL_PATH = _orig
        os.unlink(tmp.name)


def test_accion_pausar_reanudar() -> None:
    from dashboard import server
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    _orig = control.CONTROL_PATH
    control.CONTROL_PATH = tmp.name
    try:
        assert server.ejecutar_accion("pausar", {}) == {"ok": True, "pausado": True}
        assert control.esta_pausado(tmp.name) is True
        assert server.ejecutar_accion("reanudar", {}) == {"ok": True, "pausado": False}
        assert server.ejecutar_accion("nada", {})["ok"] is False
    finally:
        control.CONTROL_PATH = _orig
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_control_archivo, test_bot_no_emite_en_pausa,
             test_accion_pausar_reanudar]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
