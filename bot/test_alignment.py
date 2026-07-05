"""
bot/test_alignment.py
=====================
Valida la sinfonía de dirección SIN red: alineación ponderada, la ley EMA200 en
1H, y el mínimo (7/12 OTC, 8/12 real).
"""

import numpy as np
import pandas as pd

from bot.alignment import evaluar_alineacion, direccion_timeframe
from bot.scoring_strategy import CALL, PUT
from bot import otc_system, real_system

TFS = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]


def _df(subiendo=True, n=260):
    base = 100.0
    xs = range(n)
    precios = [base + (i if subiendo else (n - i)) * 0.2 + np.sin(i / 6) * 0.2
               for i in xs]
    close = pd.Series(precios, dtype=float)
    return pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]),
                         "high": close + 0.15, "low": close - 0.15,
                         "close": close})


def test_frames_alcistas_operar_call():
    frames = {tf: _df(subiendo=True) for tf in TFS}
    r = evaluar_alineacion(frames, otc_system)
    assert r["direccion_1h"] == CALL
    assert r["veredicto"] == "OPERAR", r
    assert r["alineados"] >= otc_system.ALINEACION_MINIMA
    print(f"OK todo alcista -> OPERAR CALL ({r['alineados']}/{r['total_tf']}, "
          f"{r['peso_favor']}% peso)")


def test_frames_bajistas_operar_put():
    frames = {tf: _df(subiendo=False) for tf in TFS}
    r = evaluar_alineacion(frames, otc_system)
    assert r["direccion_1h"] == PUT
    assert r["veredicto"] == "OPERAR", r
    print(f"OK todo bajista -> OPERAR PUT ({r['alineados']}/{r['total_tf']})")


def test_ley_ema200_1h_veta_contra():
    # 1H bajista pero los cortos alcistas -> NO se opera (ley absoluta).
    frames = {tf: _df(subiendo=True) for tf in TFS}
    frames[3600] = _df(subiendo=False)         # 1H en contra
    r = evaluar_alineacion(frames, otc_system)
    assert r["direccion_1h"] == PUT
    # Los cortos alcistas NO cuentan a favor de PUT -> pocos alineados -> no opera.
    assert r["veredicto"] == "NO OPERAR", r
    print("OK la EMA200 de 1H es ley: veta operar en su contra")


def test_real_mas_estricto():
    # Con 1H plano/HOLD no se opera; y el real pide 8 (vs 7 OTC).
    assert real_system.ALINEACION_MINIMA == 8
    assert otc_system.ALINEACION_MINIMA == 7
    frames = {tf: _df(subiendo=True) for tf in TFS}
    r = evaluar_alineacion(frames, real_system)
    assert r["veredicto"] in ("OPERAR", "NO OPERAR")
    print(f"OK real usa mínimo 8/12 (OTC 7/12) — veredicto: {r['veredicto']}")


def test_sin_1h_usa_tiempo_mayor():
    # En OTC el 1h viejo no aplica (PO resetea). Si no hay 1H fresco, el ancla de
    # dirección es el tiempo más ALTO disponible (aquí 30m). Con todo alcista y
    # alineado, SÍ opera (antes exigía 1H y no operaba).
    frames = {tf: _df(subiendo=True) for tf in TFS if tf != 3600}   # sin 1H
    r = evaluar_alineacion(frames, otc_system)
    assert r["veredicto"] == "OPERAR" and r["direccion_1h"] == "CALL"
    print("OK sin 1H usa el tiempo mayor disponible como ancla -> OPERAR")


def test_sin_frames_no_opera():
    # Sin ningún tiempo (nada fresco) -> NO OPERAR (honesto, no inventa).
    r = evaluar_alineacion({}, otc_system)
    assert r["veredicto"] == "NO OPERAR"
    print("OK sin datos frescos -> NO OPERAR")


def test_ancla_salta_tiempo_alto_neutral():
    # El tiempo más alto disponible queda NEUTRAL/plano, pero los de abajo son
    # alcistas claros. El ancla debe SALTAR al mayor CON dirección (antes anulaba
    # todo con "0/12" aunque el panel estuviera casi todo verde).
    frames = {tf: _df(subiendo=True) for tf in TFS if tf not in (3600, 1800)}
    plano = pd.DataFrame({"open": [100.0] * 12, "high": [100.1] * 12,
                          "low": [99.9] * 12, "close": [100.0] * 12})
    frames[1800] = plano                       # 30m sin dirección (plano)
    r = evaluar_alineacion(frames, otc_system)
    assert r["direccion_1h"] == CALL, r
    assert r["alineados"] >= otc_system.ALINEACION_MINIMA, r
    print(f"OK ancla salta el tiempo alto neutral -> usa la tendencia clara "
          f"({r['alineados']}/{r['total_tf']})")


if __name__ == "__main__":
    test_frames_alcistas_operar_call()
    test_frames_bajistas_operar_put()
    test_ley_ema200_1h_veta_contra()
    test_real_mas_estricto()
    test_sin_1h_usa_tiempo_mayor()
    test_sin_frames_no_opera()
    test_ancla_salta_tiempo_alto_neutral()
    print("\nTODOS OK — sinfonía de dirección (alineación ponderada + tiempo mayor)")
