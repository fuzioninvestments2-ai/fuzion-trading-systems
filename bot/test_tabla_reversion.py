"""
bot/test_tabla_reversion.py
===========================
Valida sin red la tabla de reversión por par: sobre una serie con reversión perfecta
sale un tramo ganador; una serie sin reversión no deja tramos; y `construir` guarda el
json. También comprueba que senal_reversion usa la tabla del par.
"""
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.tabla_reversion import tabla_par, construir
from bot.senal_reversion import senal, cargar_tabla


def _serie_reversion(n):
    # Reversión que PERSISTE 2 velas: pico +12 pips y luego baja -6, -6 de vuelta a la
    # base (patrón período 4). Así el borde se detecta AUNQUE se entre una vela tarde
    # (retardo=1), como en el vivo. Umbral >=8 solo cuenta el pico de +12.
    patron = [1.1000, 1.1012, 1.1006, 1.1000]
    return np.array([patron[i % 4] for i in range(n)], dtype=float)


def _serie_alterna(n):
    # Reversión de UNA sola vela (alterna): buena para ver el efecto del retardo.
    return np.array([1.10 + 0.0008 * (i % 2) for i in range(n)], dtype=float)


def test_tabla_par_detecta_borde():
    # Con el desfase real (retardo=1) y reversión que persiste 2 velas: hay borde.
    tr = tabla_par(_serie_reversion(6000), "EURUSD", tf_min=1)
    assert tr                                              # hay tramos ganadores
    assert all(wr > 52.08 for _, wr, _ in tr)             # todos por encima del break-even


def test_retardo_cambia_la_medicion():
    # D1 en una prueba: en una reversión de UNA vela, entrar al cierre del pico (retardo 0)
    # gana; entrar una vela tarde (retardo 1) la pierde. Por eso hay que medir con el
    # desfase real.
    serie = _serie_alterna(4000)
    con0 = tabla_par(serie, "EURUSD", tf_min=1, retardo=0)
    con1 = tabla_par(serie, "EURUSD", tf_min=1, retardo=1)
    assert con0                                            # entrando a tiempo: hay borde
    assert con1 == []                                     # una vela tarde: se pierde el borde


def test_tabla_par_serie_sin_reversion():
    # Tendencia monótona: no hay reversión -> sin tramos ganadores.
    c = np.array([1.10 + 0.0001 * i for i in range(2000)], dtype=float)
    assert tabla_par(c, "EURUSD", tf_min=1) == []


def test_construir_guarda_json():
    with tempfile.TemporaryDirectory() as d:
        c = _serie_reversion(6000)
        ts = np.array([1_700_000_000_000 + i * 60_000 for i in range(len(c))],
                      dtype=np.int64)
        pd.DataFrame({"timestamp": ts, "open": c, "high": c, "low": c,
                      "close": c, "volume": 1.0}).to_csv(
            os.path.join(d, "EURUSD__M1.csv.gz"), index=False, compression="gzip")
        tabla = construir(destino=d, pares=["EURUSD"])
        assert "EURUSD" in tabla
        assert isinstance(tabla["EURUSD"], dict)          # formato POR TIEMPO
        assert "1" in tabla["EURUSD"]                      # tiene el tiempo de 1m (con retardo real)
        ruta = os.path.join(d, "reversion_tabla.json")
        assert os.path.exists(ruta)
        assert cargar_tabla(ruta)["EURUSD"]["1"]           # se relee bien


def test_senal_usa_tabla_por_tiempo():
    from bot.senal_reversion import senal
    # Distinto acierto por tiempo: 1m -> 60%, 3m -> 70%. La señal debe usar el suyo.
    tabla = {"EURCHF": {"1": [[5, 60.0]], "3": [[5, 70.0]]}}
    s3 = senal([1.0800, 1.0806], "EURCHF", expiry_min=3, tabla=tabla)   # +6 pips
    s1 = senal([1.0800, 1.0806], "EURCHF", expiry_min=1, tabla=tabla)
    assert s3["probabilidad"] == 70.0
    assert s1["probabilidad"] == 60.0


def test_senal_usa_tabla_del_par():
    # Tabla propia de EURUSD que da 70% a partir de 5 pips: la señal debe reflejarla.
    tabla = {"EURUSD": [[5, 70.0]]}
    s = senal([1.1000, 1.1006], "EURUSD", tabla=tabla)    # +6 pips
    assert s["operar"] is True
    assert s["probabilidad"] == 70.0                      # usa el borde del par


def test_senal_par_sin_borde_no_opera():
    tabla = {"EURUSD": [[9, 60.0]]}                        # solo opera con >=9 pips
    s = senal([1.1000, 1.1006], "EURUSD", tabla=tabla)    # +6 pips < 9
    assert s["operar"] is False


def test_cargar_tabla_inexistente():
    assert cargar_tabla("/no/existe/x.json") == {}


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
