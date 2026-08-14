"""
tests/test_patrones_factor.py (fuzion_fx)
=========================================
Valida candle_patterns.ajuste_confianza: el patron ajusta el factor de confianza
segun el doc fuente (martillo +10% a favor CALL, doji -20% e indecision, patron en
contra -15%). SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import candle_patterns as P                           # noqa: E402


def _una_vela(o, h, l, c, prev=None):
    """Velas con una (o dos) para probar el patron de la ULTIMA."""
    O, H, L, C = [o], [h], [l], [c]
    if prev is not None:
        O = [prev[0], o]; H = [prev[1], h]; L = [prev[2], l]; C = [prev[3], c]
    return {"open": O, "high": H, "low": L, "close": C}


def test_martillo_a_favor_call_suma() -> None:
    # Cuerpo chico arriba, mecha larga abajo -> martillo (sesgo CALL).
    velas = _una_vela(1.1000, 1.1002, 1.0985, 1.1001)
    r = P.ajuste_confianza(velas, P.CALL)
    assert r["patron"] == "martillo" and abs(r["factor"] - 0.10) < 1e-9


def test_martillo_en_contra_de_put_resta() -> None:
    velas = _una_vela(1.1000, 1.1002, 1.0985, 1.1001)
    r = P.ajuste_confianza(velas, P.PUT)     # senal PUT pero el martillo es CALL
    assert abs(r["factor"] - P.CONTRADICTORIO) < 1e-9


def test_doji_penaliza_e_indecision() -> None:
    velas = _una_vela(1.1000, 1.1006, 1.0994, 1.10001)   # apertura ~ cierre
    r = P.ajuste_confianza(velas, P.CALL)
    assert r["indecision"] is True and abs(r["factor"] - P.DOJI_PENAL) < 1e-9


def test_envolvente_alcista_suma_15() -> None:
    # Vela previa bajista; actual alcista que la envuelve -> +15% a favor CALL.
    prev = (1.1010, 1.1012, 1.1000, 1.1002)              # bajista
    velas = _una_vela(1.1001, 1.1020, 1.1000, 1.1018, prev=prev)
    r = P.ajuste_confianza(velas, P.CALL)
    assert r["patron"] == "envolvente_alcista" and abs(r["factor"] - 0.15) < 1e-9


def test_sin_patron_factor_cero() -> None:
    velas = _una_vela(1.1000, 1.1010, 1.0996, 1.1006)   # mechas parejas, sin patron
    r = P.ajuste_confianza(velas, P.CALL)
    assert r["factor"] == 0.0 and r["patron"] is None


def _run_all() -> None:
    tests = [test_martillo_a_favor_call_suma, test_martillo_en_contra_de_put_resta,
             test_doji_penaliza_e_indecision, test_envolvente_alcista_suma_15,
             test_sin_patron_factor_cero]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
