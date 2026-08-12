"""
tests/test_emisor.py (fuzion_fx)
================================
Valida la construccion de la tarjeta de senal MANUAL (build_card_manual): borde
de entrada, direccion, sello educativo. El envio real (Telegram) no se prueba
(red). SIN red.
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.emisor import build_card_manual, enviar_senal_manual   # noqa: E402


def test_card_call() -> None:
    # now no alineado: entrada = proximo borde de 180s.
    c = build_card_manual("EUR/USD", 180, "CALL", nota="ojo soporte",
                          payout=83, now=1000)
    assert "*EUR/USD*" in c and "CALL (poner ARRIBA)" in c
    assert "3 min - M3" in c and "83%" in c
    assert "ojo soporte" in c
    assert "no está garantizado" in c              # sello educativo


def test_card_put_sin_pago_ni_nota() -> None:
    c = build_card_manual("GBP/JPY", 60, "PUT", now=1000)
    assert "PUT (poner ABAJO)" in c and "1 min - M1" in c
    assert "Pago del activo" not in c              # sin payout -> no aparece


def test_enviar_sin_config_no_revienta() -> None:
    # Sin telegram configurado, devuelve ok=False pero con la tarjeta armada.
    r = enviar_senal_manual("EUR/USD", 180, "CALL")
    assert r["enviados"] == 0 and "card" in r and r["ok"] in (False, True)


def _run_all() -> None:
    tests = [test_card_call, test_card_put_sin_pago_ni_nota,
             test_enviar_sin_config_no_revienta]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
