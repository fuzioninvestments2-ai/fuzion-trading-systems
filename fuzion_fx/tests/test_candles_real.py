"""
tests/test_candles_real.py (fuzion_fx)
======================================
Valida la tabla candles_real del CandleStore (Paso 2): upsert real separado de
los ticks, lectura real, price_at_real por bucket, y que el feed PRIORICE el OHLC
real sobre los ticks. SIN red (sqlite en memoria / archivo temporal).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from collector.candle_store import CandleStore       # noqa: E402
from data.price_feed import CandleStoreFeed          # noqa: E402


def test_real_separado_de_ticks() -> None:
    s = CandleStore(":memory:")
    s.upsert_candle("EUR/USD", 60, 60, 1.0, 1.0, 1.0, 1.0, 3)         # tick
    s.upsert_real_candle("EUR/USD", 60, 60, 1.10, 1.12, 1.09, 1.11, 9)  # real
    # Cada tabla mantiene lo suyo (no se pisan).
    assert s.get_candles("EUR/USD", 60)["close"] == [1.0]
    assert s.get_real_candles("EUR/USD", 60)["close"] == [1.11]
    s.close()


def test_upsert_real_reescribe_todo() -> None:
    s = CandleStore(":memory:")
    s.upsert_real_candle("EUR/USD", 300, 300, 1.0, 1.0, 1.0, 1.0, 1)
    s.upsert_real_candle("EUR/USD", 300, 300, 2.0, 2.5, 1.9, 2.1, 8)   # reenviada
    r = s.get_real_candles("EUR/USD", 300)
    assert r["open"] == [2.0] and r["close"] == [2.1] and r["high"] == [2.5]
    s.close()


def test_price_at_real_por_bucket() -> None:
    s = CandleStore(":memory:")
    s.upsert_real_candle("EUR/USD", 60, 120, 1.1, 1.2, 1.0, 1.15, 2)
    # ts=145 cae en el bucket 120 (120 + 25) -> devuelve el cierre de esa vela.
    assert s.price_at_real("EUR/USD", 60, 145) == 1.15
    # ts=200 cae en el bucket 180 (no hay vela real) -> None (no interpola).
    assert s.price_at_real("EUR/USD", 60, 200) is None
    s.close()


def test_feed_prioriza_real_sobre_ticks() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        s = CandleStore(tmp.name)
        # Ticks para 2 velas y real para 2 velas: el feed debe devolver las reales.
        for ts, c in [(60, 1.0), (120, 1.01)]:
            s.upsert_candle("EUR/USD", 60, ts, c, c, c, c, 1)
        for ts, c in [(60, 1.10), (120, 1.11)]:
            s.upsert_real_candle("EUR/USD", 60, ts, c, c, c, c, 5)
        s.close()

        feed = CandleStoreFeed(tmp.name)
        got = feed.get_candles("EUR/USD", 60)
        assert got["close"] == [1.10, 1.11]           # real, no ticks
        assert feed.price_at_real("EUR/USD", 60, 130) == 1.11
    finally:
        os.unlink(tmp.name)


def test_feed_cae_a_ticks_si_no_hay_real() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        s = CandleStore(tmp.name)
        for ts, c in [(60, 1.0), (120, 1.01)]:
            s.upsert_candle("EUR/USD", 60, ts, c, c, c, c, 1)
        s.close()
        feed = CandleStoreFeed(tmp.name)
        got = feed.get_candles("EUR/USD", 60)
        assert got["close"] == [1.0, 1.01]            # backup: ticks
    finally:
        os.unlink(tmp.name)


def _run_all() -> None:
    tests = [test_real_separado_de_ticks, test_upsert_real_reescribe_todo,
             test_price_at_real_por_bucket, test_feed_prioriza_real_sobre_ticks,
             test_feed_cae_a_ticks_si_no_hay_real]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
