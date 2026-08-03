"""
bot/test_validar_edge.py
========================
Valida sin red que la validación de edge es exigente: la corrección Bonferroni endurece
el límite; un edge amplio y estable en el tiempo se declara ROBUSTO; uno que solo gana un
año, o que lo sostiene un único par, NO pasa.
"""
import calendar
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.validar_edge import _z_bonferroni, validar


HORA_CIERRE = 22          # cae en la sesión "Cierre" (21<=h<23)


def _ms(anio):
    """ms UTC del 1 de junio de `anio` (para cortar por año sin depender de zona)."""
    return calendar.timegm(datetime.datetime(anio, 6, 1).timetuple()) * 1000


def _ops(anio, n_win, n_los, hora=HORA_CIERRE):
    t = _ms(anio)
    return ([{"hora": hora, "ts": t, "pico": 6.0, "direccion": "PUT", "gana": True}] * n_win +
            [{"hora": hora, "ts": t, "pico": 6.0, "direccion": "PUT", "gana": False}] * n_los)


def test_bonferroni_endurece():
    # Con más celdas miradas, el z exigido sube (intervalo más ancho).
    assert _z_bonferroni(1) < _z_bonferroni(32)
    assert _z_bonferroni(32) > 3.0            # ~3.16 para 32 celdas


def test_edge_robusto_pasa_las_tres():
    # Varios pares, varios años, todos ~57% con mucha muestra -> robusto.
    ops_por_par = {}
    for par in ("EURUSD", "GBPUSD", "USDCHF", "EURJPY"):
        ops = []
        for anio in range(2010, 2016):
            ops += _ops(anio, 570, 430)       # 57% cada año
        ops_por_par[par] = ops
    v = validar(ops_por_par, "Cierre", payout=92.0, tests=32)
    assert v["robusto"]
    assert v["pasa_bonferroni"] and v["pasa_anios"] and v["pasa_amplitud"]


def test_edge_de_un_solo_par_no_es_robusto():
    # Un par gana fuerte; los demás en equilibrio. Quitar el mejor par lo tumba.
    ops_por_par = {"EURUSD": []}
    for anio in range(2010, 2016):
        ops_por_par["EURUSD"] += _ops(anio, 640, 360)     # 64%: arrastra el promedio
    for par in ("GBPUSD", "USDCHF"):
        ops = []
        for anio in range(2010, 2016):
            ops += _ops(anio, 500, 500)                    # 50%: sin ventaja
        ops_por_par[par] = ops
    v = validar(ops_por_par, "Cierre", payout=92.0, tests=32)
    assert not v["pasa_amplitud"]
    assert not v["robusto"]


def test_edge_de_un_solo_anio_no_es_robusto():
    # Un año dispara el acierto; el resto en equilibrio -> no gana la mayoría de años.
    ops_por_par = {}
    for par in ("EURUSD", "GBPUSD", "USDCHF"):
        ops = _ops(2012, 900, 100)                         # 2012 altísimo
        for anio in (2010, 2011, 2013, 2014, 2015):
            ops += _ops(anio, 500, 500)                    # el resto 50%
        ops_por_par[par] = ops
    v = validar(ops_por_par, "Cierre", payout=92.0, tests=32)
    assert not v["pasa_anios"]
    assert not v["robusto"]


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
