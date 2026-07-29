"""
bot/test_sesiones.py
====================
Valida sin red las sesiones de mercado por hora UTC.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.sesiones import sesiones_activas, etiqueta, _activa


def test_activa_normal_y_cruce_medianoche():
    assert _activa(8, 17, 10) is True and _activa(8, 17, 18) is False
    assert _activa(22, 7, 23) is True and _activa(22, 7, 3) is True   # cruza medianoche
    assert _activa(22, 7, 12) is False


def test_solape_londres_ny():
    # 14:00 UTC: Londres y Nueva York abiertas (el solape fuerte).
    act = sesiones_activas(14)
    assert "Londres" in act and "Nueva York" in act
    assert etiqueta(14).startswith("Londres")       # las grandes primero


def test_solo_tokio_madrugada():
    # 02:00 UTC: Tokio (y Sídney) abiertas, Londres/NY no.
    act = sesiones_activas(2)
    assert "Tokio" in act and "Londres" not in act and "Nueva York" not in act


def test_solo_nueva_york_noche():
    # 20:00 UTC: Nueva York abierta, Londres cerrada.
    act = sesiones_activas(20)
    assert "Nueva York" in act and "Londres" not in act


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
