"""
tests/test_resolucion_honesta.py (fuzion_fx)
============================================
Valida la resolucion honesta (Paso 3): las senales se liquidan contra el OHLC
REAL de PO (candles_real); sin dato real al vencimiento se ESPERA dentro del
margen y, pasado el margen, se marca NULA (sin inventar). Las nulas no cuentan en
el win-rate. SIN red (CandleStoreFeed sobre archivo temporal + ResultsStore en
memoria).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from bots.base_bot import BaseBot                    # noqa: E402
from core.results_store import ResultsStore          # noqa: E402
from collector.candle_store import CandleStore       # noqa: E402
from data.price_feed import CandleStoreFeed          # noqa: E402

TF = 60                                              # f1_m1


def _bot_con_db():
    """BaseBot f1_m1 con feed real sobre db temporal y store en memoria."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    seed = CandleStore(tmp.name)                     # crea el esquema
    seed.close()
    bot = BaseBot("f1_m1", price_feed=CandleStoreFeed(tmp.name),
                  store=ResultsStore(":memory:"))
    return bot, tmp.name


def _guardar(bot, ts, direction, price):
    return bot.store.save_signal({"ts": ts, "pair": "EUR/USD", "timeframe": "1m",
                                  "direction": direction, "setup_id": "s1",
                                  "confirmations": 3, "price": price, "atr": 0.0})


def test_resuelve_win_contra_real() -> None:
    bot, path = _bot_con_db()
    try:
        sid = _guardar(bot, 1000, "CALL", 1.1000)
        # Vela real en el bucket que contiene el vencimiento (exp=1060 -> bucket
        # 1020) con cierre por encima de la entrada -> WIN.
        store = CandleStore(path)
        store.upsert_real_candle("EUR/USD", TF, 1020, 1.1005, 1.1012, 1.1004, 1.1010, 5)
        store.close()
        resueltas = bot.resolve_pending(now=1200)
        assert resueltas == 1
        assert bot.store.win_rate("EUR/USD") == {"trades": 1, "wins": 1, "win_pct": 100.0}
        _ = sid
    finally:
        os.unlink(path)


def test_resuelve_loss_contra_real() -> None:
    bot, path = _bot_con_db()
    try:
        _guardar(bot, 1000, "CALL", 1.1000)
        store = CandleStore(path)
        store.upsert_real_candle("EUR/USD", TF, 1020, 1.0995, 1.0999, 1.0990, 1.0992, 5)
        store.close()
        assert bot.resolve_pending(now=1200) == 1
        wr = bot.store.win_rate("EUR/USD")
        assert wr["trades"] == 1 and wr["wins"] == 0
    finally:
        os.unlink(path)


def test_espera_dentro_del_margen() -> None:
    bot, path = _bot_con_db()
    try:
        _guardar(bot, 2000, "PUT", 1.1000)           # expiry=2060, sin vela real
        bot.null_grace_seconds = 600
        # now-expiry = 10 < margen -> ni resuelve ni nulifica: sigue pendiente.
        assert bot.resolve_pending(now=2070) == 0
        assert len(bot.store.pending_older_than(2070)) == 1
    finally:
        os.unlink(path)


def test_nula_pasado_el_margen() -> None:
    bot, path = _bot_con_db()
    try:
        _guardar(bot, 2000, "PUT", 1.1000)           # expiry=2060, sin vela real
        bot.null_grace_seconds = 100
        # now-expiry = 200 > margen -> NULA (no inventa cierre).
        assert bot.resolve_pending(now=2260) == 0    # nulas no cuentan como resueltas
        assert bot.store.pending_older_than(2260) == []   # ya no esta pendiente
        assert bot.store.win_rate("EUR/USD")["trades"] == 0   # no cuenta en win-rate
    finally:
        os.unlink(path)


def test_no_usa_ticks_para_resolver() -> None:
    bot, path = _bot_con_db()
    try:
        _guardar(bot, 1000, "CALL", 1.1000)
        # Solo hay TICK (no real) en el vencimiento: NO se resuelve con el tick.
        store = CandleStore(path)
        store.upsert_candle("EUR/USD", TF, 1020, 1.2000, 1.2000, 1.2000, 1.2000, 1)
        store.close()
        bot.null_grace_seconds = 100
        assert bot.resolve_pending(now=2260) == 0    # tick ignorado -> NULA
        assert bot.store.win_rate("EUR/USD")["trades"] == 0
    finally:
        os.unlink(path)


def _run_all() -> None:
    tests = [test_resuelve_win_contra_real, test_resuelve_loss_contra_real,
             test_espera_dentro_del_margen, test_nula_pasado_el_margen,
             test_no_usa_ticks_para_resolver]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
