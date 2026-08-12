"""
tests/test_auditar_resolucion.py (fuzion_fx)
============================================
Valida el nucleo de auditoria de resolucion: seleccion de vela, GAP y deteccion
de resultados que cambiarian con la vela correcta. SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts.auditar_resolucion import (vela_de_cierre, vela_mas_cercana,   # noqa: E402
                                        auditar_senal, _resultado)


def test_vela_de_cierre_replica_price_at() -> None:
    velas = [(100, 1.10, 3), (400, 1.11, 2), (700, 1.12, 5)]
    # primera con ts >= 450 -> la de ts=700 (salta la de 400).
    assert vela_de_cierre(velas, 450) == (700, 1.12, 5)
    assert vela_de_cierre(velas, 50) == (100, 1.10, 3)
    assert vela_de_cierre(velas, 800) is None


def test_vela_mas_cercana() -> None:
    velas = [(100, 1.10, 1), (400, 1.11, 1), (700, 1.12, 1)]
    assert vela_mas_cercana(velas, 450)[0] == 400    # 450 mas cerca de 400 que 700
    assert vela_mas_cercana([], 10) is None


def test_resultado_binario() -> None:
    assert _resultado("PUT", 1.100, 1.090) == "win"    # bajo -> PUT gana
    assert _resultado("PUT", 1.100, 1.110) == "loss"
    assert _resultado("CALL", 1.100, 1.110) == "win"
    assert _resultado("CALL", 1.100, 1.100) == "tie"


def test_auditar_detecta_win_falso() -> None:
    # PUT: entrada 1.09584. Vencimiento cae en una zona donde la UNICA vela
    # >= expiry es vieja/baja (1.09528) -> el bot marca WIN. Pero la vela mas
    # cercana al vencimiento (1.09590, precio real que siguio subiendo) daria LOSS.
    tf = 180
    ts = 1_000_000
    expiry = ts + tf                                   # 1_000_180
    velas = [
        (1_000_000, 1.09528, 1),                       # vieja (antes del venc.)
        (1_000_170, 1.09590, 4),                       # la mas cercana al venc.
        (1_000_600, 1.09528, 1),                       # la 1a con ts >= expiry (lejana)
    ]
    sig = {"ts": ts, "pair": "GBP/CHF", "direction": "PUT",
           "price": 1.09584, "result": "win"}
    d = auditar_senal(sig, velas, tf)
    assert d["close_usado"] == 1.09528                 # lo que uso el bot (WIN falso)
    assert d["gap_seg"] == 1_000_600 - expiry          # vela de cierre lejana
    assert d["result_recalculado"] == "loss"           # con la vela real: LOSS
    assert d["cambia"] is True


def test_auditar_sin_cambio_cuando_coincide() -> None:
    tf = 60
    ts = 500_000
    expiry = ts + tf
    velas = [(ts, 1.100, 2), (expiry, 1.090, 3)]       # vela justo en el venc.
    sig = {"ts": ts, "pair": "EUR/USD", "direction": "PUT",
           "price": 1.100, "result": "win"}
    d = auditar_senal(sig, velas, tf)
    assert d["gap_seg"] == 0 and d["cambia"] is False


def _run_all() -> None:
    tests = [test_vela_de_cierre_replica_price_at, test_vela_mas_cercana,
             test_resultado_binario, test_auditar_detecta_win_falso,
             test_auditar_sin_cambio_cuando_coincide]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
