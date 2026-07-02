"""
bot/test_chart.py
================
Valida el gráfico: horas ANCLADAS al reloj del usuario (no a la zona horaria del
bróker) y que dibuja sin errores. Sin red, determinista (hora de referencia fija).
"""

import os
from datetime import datetime

import pandas as pd

from bot.chart import _etiquetas_hora, draw_candles


def _df(n=10, tf_ms=60000):
    ts0 = 1_700_000_000_000
    return pd.DataFrame([{"timestamp": ts0 + i * tf_ms, "open": 1.10,
                          "high": 1.11, "low": 1.09, "close": 1.10, "volume": 1}
                         for i in range(n)])


def test_ultima_hora_es_ahora():
    # La vela de la derecha = "ahora" (el reloj del usuario).
    ahora = datetime(2026, 7, 2, 19, 31, 0)
    pos, lab = _etiquetas_hora(_df(10), ahora=ahora)
    assert lab[-1] == "19:31", lab
    # Y retrocede 1 min por vela (M1): la penúltima marca 19:30.
    assert lab[-2] == "19:30", lab
    print(f"OK última hora = ahora ({lab[-1]}), retrocede por intervalo")


def test_formato_segundos_en_subminuto():
    # Velas de 15s -> formato con segundos.
    ahora = datetime(2026, 7, 2, 19, 31, 0)
    pos, lab = _etiquetas_hora(_df(8, tf_ms=15000), ahora=ahora)
    assert any(l.count(":") == 2 for l in lab), lab   # HH:MM:SS
    print(f"OK sub-minuto usa HH:MM:SS: {lab[-1]}")


def test_sin_velas_no_rompe():
    assert _etiquetas_hora(pd.DataFrame()) == (None, None)
    print("OK sin velas -> (None, None)")


def test_dibuja_png():
    path = os.path.join(os.path.dirname(__file__), "..", "charts_tmp_test2.png")
    draw_candles(_df(20), "AUD/CAD OTC", "M1", path,
                 levels={"resistencias": [1.11], "soportes": [1.09]})
    assert os.path.exists(path) and os.path.getsize(path) > 1000
    os.remove(path)
    print("OK dibuja PNG con niveles")


if __name__ == "__main__":
    test_ultima_hora_es_ahora()
    test_formato_segundos_en_subminuto()
    test_sin_velas_no_rompe()
    test_dibuja_png()
    print("\nTODOS OK — gráfico (horas ancladas al reloj + dibujo)")
