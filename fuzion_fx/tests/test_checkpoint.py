"""
tests/test_checkpoint.py (fuzion_fx)
====================================
Valida el Sistema de Checkpoint Cuantico: pre-filtro de 10s y alerta de
autocorreccion. SIN red ni esperas reales (prefilter_seconds=0, timers off).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.results_store import ResultsStore                    # noqa: E402
from core.signal_engine import CALL, PUT, NEUTRAL              # noqa: E402
from data.price_feed import InMemoryPriceFeed                  # noqa: E402
from bots.base_bot import BaseBot                              # noqa: E402


def _res(signal, rsi=50.0, votes=None):
    return {"signal": signal, "confirmations": 3,
            "votes": votes or {"ema": 1, "rsi": 1, "macd": 1, "bollinger": -1},
            "confirming": ["ema", "macd", "rsi"],
            "setup_id": f"{signal}|ema,macd,rsi", "atr": 0.0004, "price": 1.10,
            "readings": {"rsi": rsi, "macd_hist": 0.0001}}


class _SeqEngine:
    """Devuelve resultados en secuencia (uno por llamada a analyze)."""
    def __init__(self, results):
        self.results = list(results)
        self.i = 0

    def analyze(self, candles):
        r = self.results[min(self.i, len(self.results) - 1)]
        self.i += 1
        return r


class _Notif:
    def __init__(self):
        self.texts = []
        self.alerts = []

    def send(self, msg, photo_buffer=None):
        self.texts.append(msg); return True

    def send_text(self, msg, parse_mode="Markdown"):
        self.texts.append(msg); return True

    def send_alert(self, msg, parse_mode="Markdown"):
        self.alerts.append(msg); return True


def _feed():
    f = InMemoryPriceFeed()
    c = [1.10 + 0.0001 * i for i in range(40)]
    f.set_candles("EUR/USD", {"open": c, "high": [x + 0.0002 for x in c],
                              "low": [x - 0.0002 for x in c], "close": c})
    return f


def _bot(engine, notif=None):
    bot = BaseBot("f1_m1", price_feed=_feed(), store=ResultsStore(":memory:"),
                  notifier=notif)
    bot.pairs = ["EUR/USD"]
    bot.prefilter_seconds = 0
    bot.signal_cooldown = 0            # sin esperas reales
    bot._schedule_enabled = False        # sin timers de fondo
    bot.engine = engine
    return bot


def test_prefiltro_cambia_no_emite() -> None:
    # scan ve CALL, pre-filtro ve PUT -> NO emite.
    bot = _bot(_SeqEngine([_res(CALL), _res(PUT)]), _Notif())
    assert bot.scan_once(now=1000.0) == []


def test_prefiltro_coincide_emite() -> None:
    # scan ve CALL, pre-filtro ve CALL -> emite.
    notif = _Notif()
    bot = _bot(_SeqEngine([_res(CALL), _res(CALL)]), notif)
    emitidas = bot.scan_once(now=1000.0)
    assert len(emitidas) == 1 and emitidas[0]["direction"] == CALL
    assert len(notif.texts) == 1                 # se mando la tarjeta


def test_checkpoint_misma_direccion_no_alerta() -> None:
    notif = _Notif()
    bot = _bot(_SeqEngine([_res(CALL)]), notif)   # recalculo da CALL
    r = bot._run_checkpoint("EUR/USD", CALL, _res(CALL), ts_emitida=1000.0)
    assert r is None and notif.alerts == []


def test_checkpoint_direccion_distinta_alerta() -> None:
    notif = _Notif()
    bot = _bot(_SeqEngine([_res(PUT, rsi=35.0)]), notif)   # se dio vuelta a PUT
    orig = _res(CALL, rsi=65.0)
    r = bot._run_checkpoint("EUR/USD", CALL, orig, ts_emitida=1000.0)
    assert r is not None
    assert len(notif.alerts) == 1
    a = notif.alerts[0]
    assert "AUTOCORRECCION" in a and "EUR/USD" in a
    assert "CALL" in a and "PUT" in a
    assert "RSI" in a                              # describe RSI 65 -> 35


def _run_all() -> None:
    tests = [test_prefiltro_cambia_no_emite, test_prefiltro_coincide_emite,
             test_checkpoint_misma_direccion_no_alerta,
             test_checkpoint_direccion_distinta_alerta]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
