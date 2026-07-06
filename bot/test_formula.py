"""
bot/test_formula.py
===================
Valida SIN red la FÓRMULA DE LA DANZA: score ponderado por dirección×fuerza×peso,
zona S/R y gatillo en corto. Tendencia clara -> OPERAR en su dirección; mezcla sin
fuerza -> NO OPERAR.
"""
import numpy as np
import pandas as pd
from bot.formula import calcular_danza
from bot import otc_system

TFS = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]


def _df(subiendo=True, n=260):
    xs = [100 + (i if subiendo else (n - i)) * 0.2 + np.sin(i / 6) * 0.2
          for i in range(n)]
    c = pd.Series(xs, dtype=float)
    return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                         "high": c + 0.15, "low": c - 0.15, "close": c})


def _plano(n=260):
    c = pd.Series([100.0] * n, dtype=float)   # precio constante: sin dirección
    return pd.DataFrame({"open": c, "high": c + 0.01, "low": c - 0.01, "close": c})


def test_tendencia_alcista_opera_call():
    frames = {tf: _df(subiendo=True) for tf in TFS}
    r = calcular_danza(frames, otc_system, 300)
    assert r["direccion_1h"] == "CALL", r
    assert r["veredicto"] == "OPERAR", r
    assert r["gatillo"] is True
    assert r["score"] > 0
    print(f"OK alcista -> OPERAR CALL (score {r['score']}, fuerza {r['peso_favor']}%)")


def test_tendencia_bajista_opera_put():
    frames = {tf: _df(subiendo=False) for tf in TFS}
    r = calcular_danza(frames, otc_system, 300)
    assert r["direccion_1h"] == "PUT" and r["veredicto"] == "OPERAR", r
    assert r["score"] < 0
    print(f"OK bajista -> OPERAR PUT (score {r['score']})")


def test_mercado_plano_no_opera():
    frames = {tf: _plano() for tf in TFS}
    r = calcular_danza(frames, otc_system, 300)
    assert r["veredicto"] == "NO OPERAR", r
    print(f"OK plano/sin fuerza -> NO OPERAR (score {r['score']})")


def test_tendencia_corta_fuerte_cuenta():
    # Solo los tiempos CORTOS con tendencia fuerte (altos planos): la danza debe
    # reconocer la tendencia corta (no exige que manden los altos).
    frames = {tf: _df(subiendo=True) for tf in (5, 10, 15, 30, 60, 120)}
    frames.update({tf: _plano() for tf in (300, 600, 900, 1800, 3600)})
    r = calcular_danza(frames, otc_system, 60)
    assert r["direccion_1h"] == "CALL" and r["veredicto"] == "OPERAR", r
    print(f"OK tendencia CORTA fuerte -> OPERAR CALL (score {r['score']}) "
          f"— 'corta pero alta sigue'")


def _giro_baja(n=260, caida=40):
    # Sube casi todo el tramo y CAE fuerte al final (giro brusco): las EMAs siguen
    # marcando UP (retraso), pero el movimiento REAL de ahora es DOWN.
    xs = [100 + i * 0.15 for i in range(n - caida)]
    ult = xs[-1]
    xs += [ult - j * 0.6 for j in range(1, caida + 1)]     # caída fuerte
    c = pd.Series(xs, dtype=float)
    return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                         "high": c + 0.1, "low": c - 0.1, "close": c})


def test_giro_brusco_momentum_manda():
    frames = {tf: _giro_baja() for tf in TFS}
    r = calcular_danza(frames, otc_system, 300)
    # El movimiento real de AHORA es a la baja -> el momentum debe llevar la
    # dirección a PUT, aunque las EMAs (con retraso) aún marquen UP.
    assert r["direccion_1h"] == "PUT", r
    print(f"OK giro brusco: momentum manda -> PUT (score {r['score']})")


if __name__ == "__main__":
    test_tendencia_alcista_opera_call()
    test_tendencia_bajista_opera_put()
    test_mercado_plano_no_opera()
    test_tendencia_corta_fuerte_cuenta()
    test_giro_brusco_momentum_manda()
    print("\nTODOS OK — fórmula de la danza")
