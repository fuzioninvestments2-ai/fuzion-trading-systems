"""
tests/test_modos.py (fuzion_fx)
===============================
Valida los MODOS (lento/normal/rapido): parametros por modo, el control que los
guarda/lee, y que el bot los APLIQUE en vivo (convergencia, confirmaciones y
tiempos). SIN red.
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.modos import params_modo, MODOS, MODO_DEFAULT        # noqa: E402
from core import control                                       # noqa: E402
from core.results_store import ResultsStore                    # noqa: E402
from data.price_feed import StubPriceFeed                      # noqa: E402
from bots.base_bot import BaseBot                              # noqa: E402


def test_params_por_modo() -> None:
    r = params_modo("rapido")
    assert r["min_confirmations"] == 2 and r["scan_interval"] == 15
    lento = params_modo("lento")
    assert lento["min_confirmations"] == 3 and lento["umbral_convergencia"] >= 0.5
    # rapido busca mas: umbral mas bajo y cadencia mas rapida que lento.
    assert r["umbral_convergencia"] < lento["umbral_convergencia"]
    assert r["scan_interval"] < lento["scan_interval"]
    # Desconocido -> default.
    assert params_modo("xxx") == params_modo(MODO_DEFAULT)
    # Es COPIA: mutar el resultado no toca el registro.
    r["min_confirmations"] = 99
    assert MODOS["rapido"]["min_confirmations"] == 2


def test_control_modo_roundtrip() -> None:
    p = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
    try:
        assert control.get_modo(p) == "rapido"          # sin dato -> default
        control.set_modo("lento", p)
        assert control.get_modo(p) == "lento"
        control.set_modo("basura", p)                   # invalido -> rapido
        assert control.get_modo(p) == "rapido"
    finally:
        os.unlink(p)


def test_bot_aplica_modo() -> None:
    bot = BaseBot("f1_m1", price_feed=StubPriceFeed(), store=ResultsStore(":memory:"))
    modo = bot.aplicar_modo()
    p = params_modo(modo)
    assert bot.engine.min_confirmations == p["min_confirmations"]
    assert bot.mtf.umbral == p["umbral_convergencia"]
    assert bot.min_tf_convergencia == p["min_tf_convergencia"]


def _run_all() -> None:
    tests = [test_params_por_modo, test_control_modo_roundtrip, test_bot_aplica_modo]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
