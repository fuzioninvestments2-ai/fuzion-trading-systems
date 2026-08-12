"""
tests/test_multi_timeframe.py (fuzion_fx)
=========================================
Valida el analizador de CONVERGENCIA multi-temporalidad (la foto completa):
- Todas las temporalidades suben -> CALL con convergencia alta.
- Todas bajan -> PUT.
- Contradiccion (medio sube, corto+largo bajan y se compensan) -> NEUTRAL.
- Temporalidad con pocas velas -> no vota.
SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.config import get_bot_config                       # noqa: E402
from core.multi_timeframe import MultiTimeframeAnalyzer        # noqa: E402
from core.signal_engine import CALL, PUT, NEUTRAL              # noqa: E402


def _serie(subiendo: bool):
    base = 1.1000
    paso = 0.00006 if subiendo else -0.00006
    close = [base + paso * i for i in range(40)]
    return {"open": close[:], "high": [c + 2e-4 for c in close],
            "low": [c - 2e-4 for c in close], "close": close}


def _an():
    return MultiTimeframeAnalyzer(get_bot_config("f1_m1")["indicators"])


def test_todas_suben_call() -> None:
    an = _an()
    sube = _serie(True)
    r = an.analizar({60: sube, 120: sube, 180: sube, 300: sube, 600: sube})
    assert r["signal"] == CALL
    assert r["convergencia"] >= 0.5
    assert r["alineadas"] == r["total"] and r["total"] >= 4


def test_todas_bajan_put() -> None:
    an = _an()
    baja = _serie(False)
    r = an.analizar({60: baja, 180: baja, 300: baja})
    assert r["signal"] == PUT


def test_contradiccion_neutral() -> None:
    an = _an()
    sube, baja = _serie(True), _serie(False)
    # corto baja (0.15), medio sube (0.50), largo baja (0.35) -> score 0 -> NEUTRAL.
    velas = {15: baja, 30: baja,
             60: sube, 120: sube, 180: sube, 300: sube,
             600: baja, 900: baja, 1800: baja, 3600: baja}
    r = an.analizar(velas)
    assert r["signal"] == NEUTRAL
    assert r["convergencia"] < 0.35


def test_pocas_velas_no_vota() -> None:
    an = _an()
    assert an._lean_de_tf({"close": [1.0, 2.0, 3.0]}) == 0
    assert an._lean_de_tf(None) == 0


def test_solo_medio_disponible() -> None:
    an = _an()
    sube = _serie(True)
    # Solo el grupo medio con datos: el peso del grupo se reparte y domina.
    r = an.analizar({60: sube, 120: sube, 180: sube, 300: sube})
    assert r["signal"] == CALL
    assert r["convergencia"] >= 0.5


def _run_all() -> None:
    tests = [test_todas_suben_call, test_todas_bajan_put,
             test_contradiccion_neutral, test_pocas_velas_no_vota,
             test_solo_medio_disponible]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
