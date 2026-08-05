"""
tests/test_src_facades.py
=========================
Valida las fachadas de FASE 2 en `src/` (conexion, indicadores, vwap,
patrones, tarjeta). SIN red.

PORQUE: cada fachada debe exponer EXACTAMENTE el simbolo real de `bot.*`, sin
copiar ni alterar. Se comprueba identidad de objetos (`is`) y que los alias del
namespace limpio apuntan al original.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

# Modulos reales
from bot import pocket_client as pc                 # noqa: E402
from bot import scoring_strategy as ss              # noqa: E402
from bot import candle_patterns as cp               # noqa: E402
from bot import vwap as vw                           # noqa: E402
from bot import escaner_reversion as er             # noqa: E402

# Fachadas limpias
from src.core import connection_manager as cm       # noqa: E402
from src.indicators import indicators as ind        # noqa: E402
from src.indicators import candle_patterns as cp2   # noqa: E402
from src.indicators import vwap as vw2               # noqa: E402
from src.telegram import card_formatter as card     # noqa: E402


def test_connection_manager() -> None:
    # ConnectionManager es la MISMA clase (alias), no una subclase.
    assert cm.ConnectionManager is pc.PocketOptionClient
    assert cm.URL_DEMO == pc.URL_DEMO
    assert cm.URL_REAL == pc.URL_REAL


def test_indicators() -> None:
    assert ind.ScoringStrategy is ss.ScoringStrategy
    assert ind.weights_for is ss.weights_for
    assert ind.regime is ss.regime
    assert ind.BASE_WEIGHTS is ss.BASE_WEIGHTS


def test_candle_patterns() -> None:
    assert cp2.detect_patterns is cp.detect_patterns
    assert cp2.CALL == cp.CALL and cp2.PUT == cp.PUT


def test_vwap() -> None:
    assert vw2.vwap is vw.vwap
    assert vw2.vwap_signal is vw.vwap_signal


def test_card_formatter() -> None:
    # format_card es alias de tarjeta; escanear/resumen reexportados tal cual.
    assert card.format_card is er.tarjeta
    assert card.escanear is er.escanear
    assert card.resumen is er.resumen
    assert card.VENTANA_ENTRADA_SEG == er.VENTANA_ENTRADA_SEG


def _run_all() -> None:
    tests = [test_connection_manager, test_indicators, test_candle_patterns,
             test_vwap, test_card_formatter]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
