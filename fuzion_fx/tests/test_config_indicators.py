"""
tests/test_config_indicators.py (fuzion_fx)
===========================================
Valida core/config.py (carga de bots.yaml + ${ENV}) e indicadores base. SIN red.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import config                                         # noqa: E402
from indicators.ema import ema, calculate_ema_pair              # noqa: E402
from indicators.rsi import rsi                                  # noqa: E402
from indicators.macd import macd                                # noqa: E402
from indicators.bollinger import bollinger                      # noqa: E402
from indicators.atr import atr                                  # noqa: E402
from indicators import pips                                     # noqa: E402


def test_config_bots() -> None:
    assert config.bot_ids() == ["f1_m1", "f2_m2", "f3_m3", "f4_m5"]
    b = config.get_bot_config("f4_m5")
    assert b["timeframe_seconds"] == 300
    assert b["signal"]["min_confirmations"] == 4
    assert len(b["pairs"]) == 22
    assert os.path.isabs(b["db_path"])


def test_config_env() -> None:
    os.environ["TELEGRAM_BOT_TOKEN"] = "TOK123"
    os.environ["TELEGRAM_CHANNEL_ID"] = "-100777"
    b = config.get_bot_config("f1_m1")
    assert b["telegram"]["bot_token"] == "TOK123"
    assert b["telegram"]["channel_id"] == "-100777"
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ.pop("TELEGRAM_CHANNEL_ID", None)


def test_indicadores() -> None:
    assert abs(ema([5.0] * 40, 9) - 5.0) < 1e-9
    ef, es = calculate_ema_pair(list(range(1, 60)), 9, 21)
    assert ef > es                                    # subida: rapida sobre lenta
    assert rsi(list(np.linspace(1, 2, 60)), 14) > 70
    m, s, h = macd(list(np.linspace(1, 2, 80)))
    assert h > 0
    up, mid, low = bollinger(list(np.linspace(1.0, 1.02, 40)))
    assert low < mid < up
    high = np.array([12.0] * 6); lo = np.array([10.0] * 6); cl = np.array([11.0] * 6)
    assert abs(atr(high, lo, cl, 3) - 2.0) < 1e-9
    assert pips.pip_size("USD/JPY") == 0.01
    assert pips.pip_size("EUR/USD") == 0.0001


def _run_all() -> None:
    tests = [test_config_bots, test_config_env, test_indicadores]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
