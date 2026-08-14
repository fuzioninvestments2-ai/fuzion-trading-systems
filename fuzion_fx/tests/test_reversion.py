"""
tests/test_reversion.py (fuzion_fx)
===================================
Valida el motor HIBRIDO (Opcion C): reversion tras pico GENERA + cuantico FILTRA.
 - core/reversion.senal: pico grande -> opera EN CONTRA; pico chico/anomalo -> no;
   pip JPY correcto; direccion invertida al pico.
 - base_bot.analisis_hibrido: emite cuando hay reversion y el cuantico no contradice;
   VETA cuando el cuantico apunta fuerte en contra; NO veta contradiccion debil.
SIN red, SIN datos OTC (series sinteticas).
"""
from __future__ import annotations

import logging
import os
import sys
import types

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import reversion, indicator_set                        # noqa: E402
from bots.base_bot import BaseBot                                 # noqa: E402


# --------------------------------------------------------- core/reversion.senal
def test_pico_grande_opera_en_contra() -> None:
    # Sube 7 pips en la ultima vela -> se espera reversion PUT, con acierto OOS medido.
    r = reversion.senal([1.10000, 1.10070], "EURUSD", expiry_min=3)
    assert r["operar"] is True
    assert r["direccion"] == "PUT"                    # subio -> apuesta a que baja
    assert r["probabilidad"] == 54.6                  # tramo de 6-7 pips en TABLA_OOS


def test_pico_baja_opera_call() -> None:
    r = reversion.senal([1.10060, 1.10000], "EURUSD", expiry_min=3)
    assert r["operar"] is True and r["direccion"] == "CALL"


def test_pico_chico_no_opera() -> None:
    r = reversion.senal([1.10000, 1.10020], "EURUSD", expiry_min=3)   # 2 pips < piso 4
    assert r["operar"] is False


def test_pico_anomalo_no_opera() -> None:
    r = reversion.senal([1.10000, 1.10500], "EURUSD", expiry_min=3)   # 50 pips > techo
    assert r["operar"] is False


def test_pip_jpy() -> None:
    # JPY: pip 0.01. Subir 0.06 = 6 pips -> opera.
    r = reversion.senal([150.00, 150.06], "USDJPY", expiry_min=3)
    assert r["operar"] is True and r["direccion"] == "PUT"


# --------------------------------------------------------- base_bot.analisis_hibrido
def _velas(n=80, base=1.10000):
    c = list(np.linspace(base, base, n))
    return {"open": c, "high": [x * 1.0002 for x in c],
            "low": [x * 0.9998 for x in c], "close": c}


def _bot_falso(qr_forzado):
    """Objeto minimo con lo que analisis_hibrido/_result_desde_reversion necesitan,
    reusando los metodos REALES de BaseBot (sin construir el bot completo)."""
    fake = types.SimpleNamespace()
    fake.timeframe_seconds = 180                       # bot de 3m -> expiry 3
    fake._rev_tabla = None                             # tabla global OOS
    fake.log = logging.getLogger("test_hibrido")
    # 1m con pico de +6 pips en la ultima vela -> reversion PUT.
    velas_1m = {"open": [1.10000, 1.10000], "high": [1.10000, 1.10060],
                "low": [1.10000, 1.10000], "close": [1.10000, 1.10060]}
    fake.feed = types.SimpleNamespace(
        get_candles=lambda pair, tf: velas_1m if tf == 60 else _velas())
    fake.analisis_cuantico = lambda pair: qr_forzado   # cuantico controlado
    fake.analisis_hibrido = types.MethodType(BaseBot.analisis_hibrido, fake)
    fake._result_desde_reversion = types.MethodType(BaseBot._result_desde_reversion, fake)
    return fake


def test_hibrido_emite_si_cuantico_no_hay_datos() -> None:
    fake = _bot_falso(qr_forzado=None)                 # cuantico sin datos -> no veta
    res = fake.analisis_hibrido("EUR/USD", _velas())
    assert res is not None
    assert res["signal"] == "PUT" and res["veredicto"] == "OPERAR"
    assert res["setup_id"].startswith("PUT|H|")


def test_hibrido_veta_si_cuantico_contradice_fuerte() -> None:
    qr = {"direccion": indicator_set.CALL, "probabilidad": 0.85,
          "alineacion": 0.70, "n_alineados": 5}
    fake = _bot_falso(qr_forzado=qr)                   # CALL fuerte vs reversion PUT
    assert fake.analisis_hibrido("EUR/USD", _velas()) is None


def test_hibrido_no_veta_contradiccion_debil() -> None:
    qr = {"direccion": indicator_set.CALL, "probabilidad": 0.60,   # < UMBRAL_OPCIONAL
          "alineacion": 0.50, "n_alineados": 2}
    fake = _bot_falso(qr_forzado=qr)
    res = fake.analisis_hibrido("EUR/USD", _velas())
    assert res is not None and res["signal"] == "PUT"


# ------------------------------------------------ scan_once end-to-end (emite)
def _serie(n=80, base=1.10000, spike=0.0):
    rng = np.random.RandomState(3)
    c = list(base + np.cumsum(rng.normal(0, 0.00002, n)))   # wiggle chico -> atr>0
    if spike:
        c[-1] = c[-2] + spike                               # ultima vela: salto
    o = [c[0]] + c[:-1]
    return {"open": o, "high": [max(a, b) + 1e-5 for a, b in zip(o, c)],
            "low": [min(a, b) - 1e-5 for a, b in zip(o, c)],
            "close": c, "volume": [0.0] * n}


class _FeedSpike:
    """1m con pico de +6 pips (reversion PUT); resto de tiempos planos (cuantico
    debil -> no veta). Pago en banda."""
    def get_candles(self, pair, tf, count=200):
        return _serie(spike=0.0006) if tf == 60 else _serie(spike=0.0)

    def get_payout(self, pair):
        return 80.0


def test_scan_hibrido_emite_reversion() -> None:
    from core.results_store import ResultsStore
    from bots.base_bot import BaseBot
    bot = BaseBot("f3_m3", price_feed=_FeedSpike(), store=ResultsStore(":memory:"))
    bot.motor = "hibrido"                          # forzado: en config quedo en cuantico
    bot.signal_cooldown = 0
    bot.prefilter_seconds = 0
    bot._schedule_enabled = False
    emit = bot.scan_once(now=1000.0)
    assert emit, "el hibrido DEBE emitir con un pico de 6 pips (era el bug del silencio)"
    assert emit[0]["direction"] == "PUT"
    assert "|H|" in emit[0]["setup_id"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  OK  {fn.__name__}")
    print(f"{len(fns)} tests OK (sin red, sin OTC)")


if __name__ == "__main__":
    _run_all()
