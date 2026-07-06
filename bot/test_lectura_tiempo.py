"""
bot/test_lectura_tiempo.py
==========================
Valida SIN red la lectura POR TIEMPO: la dirección la marca la regla del tiempo
(tabla del trader) y la fuerza = cuántos de los 10 indicadores confirman.
"""
import numpy as np
import pandas as pd
from bot.lectura_tiempo import leer_tiempo, detalle_texto
from bot.scoring_strategy import CALL, PUT
from bot import otc_system


def _df(subiendo=True, n=260):
    xs = [100 + (i if subiendo else (n - i)) * 0.2 + np.sin(i / 6) * 0.2
          for i in range(n)]
    c = pd.Series(xs, dtype=float)
    return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                         "high": c + 0.15, "low": c - 0.15, "close": c})


def test_tendencia_alcista_1h_call_con_fuerza():
    lec = leer_tiempo(_df(subiendo=True), 3600, otc_system)   # 1H = EMA200
    assert lec["dir"] == CALL, lec
    assert 0.0 <= lec["fuerza"] <= 1.0
    assert isinstance(detalle_texto(lec), str)
    print(f"OK 1H alcista -> CALL, fuerza {lec['fuerza']:.0%}, {detalle_texto(lec)}")


def test_tendencia_bajista_1h_put():
    lec = leer_tiempo(_df(subiendo=False), 3600, otc_system)
    assert lec["dir"] == PUT, lec
    print(f"OK 1H bajista -> PUT, fuerza {lec['fuerza']:.0%}")


def test_fuerza_es_fraccion_de_indicadores():
    lec = leer_tiempo(_df(subiendo=True), 300, otc_system)     # 5m
    # fuerza = confirman / 10, y confirman son claves reales de indicadores.
    assert abs(lec["fuerza"] - len(lec["confirman"]) / 10.0) < 1e-9
    print(f"OK fuerza = {len(lec['confirman'])}/10 indicadores confirmando")


if __name__ == "__main__":
    test_tendencia_alcista_1h_call_con_fuerza()
    test_tendencia_bajista_1h_put()
    test_fuerza_es_fraccion_de_indicadores()
    print("\nTODOS OK — lectura por tiempo (baile indicadores x tiempos)")
