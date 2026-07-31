"""
bot/test_buscar_edge.py
=======================
Valida sin red la búsqueda de edge: el límite inferior de Wilson castiga la muestra chica
(un 70% de 10 señales NO gana), premia el edge con muestra grande, y el corte por sesión
aísla la única franja horaria con ventaja real.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.buscar_edge import _wilson_low, _celda, buscar


def _ops(hora, pico, n_win, n_los):
    return ([{"hora": hora, "pico": pico, "direccion": "PUT", "gana": True}] * n_win +
            [{"hora": hora, "pico": pico, "direccion": "PUT", "gana": False}] * n_los)


def test_wilson_castiga_muestra_chica():
    # 70% de 10 señales: el límite inferior cae MUY por debajo (no se puede afirmar edge).
    assert _wilson_low(7, 10) < 45
    # 70% de 1000 señales: el límite inferior sigue alto (edge real).
    assert _wilson_low(700, 1000) > 65


def test_celda_no_gana_sin_muestra():
    # Acierto altísimo pero solo 20 señales: no supera el mínimo -> NO gana.
    c = _celda(_ops(8, 6.0, 15, 5), equilibrio=52.08, min_n=200)
    assert c["wr"] == 75.0
    assert not c["gana"]


def test_celda_gana_con_edge_y_muestra():
    # 60% de 1000 señales, equilibrio 52.08: límite inferior ~57% > equilibrio -> GANA.
    c = _celda(_ops(8, 6.0, 600, 400), equilibrio=52.08, min_n=200)
    assert c["gana"]
    assert c["low"] > 52.08


def test_buscar_aisla_sesion_ganadora():
    # Londres (hora 8) tiene edge real; Asia (hora 2) es ruido a 50%. La búsqueda debe
    # marcar SOLO Londres como ganadora en el corte por sesión.
    ops = {"EURUSD": {1: _ops(8, 6.0, 600, 400) + _ops(2, 6.0, 500, 500)}}
    res = buscar(ops, payout=92.0, min_n=200)
    ganadoras_sesion = [g for g in res["ganadoras"] if g["tipo"] == "sesión"]
    claves = {g["clave"] for g in ganadoras_sesion}
    assert any("Londres" in k for k in claves)
    assert not any("Asia" in k for k in claves)


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
