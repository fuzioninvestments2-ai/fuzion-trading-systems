"""
bot/test_vwap.py
================
Valida el VWAP (nivel de referencia) y su sesgo. Sin red, determinista.
"""

import pandas as pd

from bot.vwap import vwap, vwap_signal, CALL, PUT, HOLD


def _df(velas, vols=None):
    """velas: lista de (o,h,l,c); vols opcional (tick-count por vela)."""
    df = pd.DataFrame(velas, columns=["open", "high", "low", "close"])
    if vols is not None:
        df["volume"] = vols
    return df


def test_vwap_promedio_sin_volumen():
    # Sin volumen -> promedio simple del precio típico (h+l+c)/3.
    df = _df([(10, 10, 10, 10), (20, 20, 20, 20)])
    assert vwap(df) == 15.0
    print("OK VWAP sin volumen = promedio simple")


def test_vwap_ponderado_por_volumen():
    # La vela con más volumen "tira" del VWAP hacia su precio.
    df = _df([(10, 10, 10, 10), (20, 20, 20, 20)], vols=[1, 3])
    # (10*1 + 20*3) / 4 = 70/4 = 17.5
    assert vwap(df) == 17.5
    print("OK VWAP ponderado por volumen (ticks)")


def test_precio_encima_es_call():
    # Serie que sube: el último precio queda por encima del VWAP -> sesgo CALL.
    velas = [(100 + i, 100 + i, 100 + i, 100 + i) for i in range(10)]
    r = vwap_signal(_df(velas))
    assert r["side"] == CALL and r["dist_pct"] > 0
    print(f"OK precio encima del VWAP -> CALL ({r['dist_pct']:+.2f}%)")


def test_precio_debajo_es_put():
    velas = [(100 - i, 100 - i, 100 - i, 100 - i) for i in range(10)]
    r = vwap_signal(_df(velas))
    assert r["side"] == PUT and r["dist_pct"] < 0
    print(f"OK precio debajo del VWAP -> PUT ({r['dist_pct']:+.2f}%)")


def test_pegado_al_vwap_es_hold():
    # Precio casi igual al VWAP -> dentro de la banda neutral -> HOLD.
    velas = [(100, 100, 100, 100) for _ in range(10)]
    r = vwap_signal(_df(velas))
    assert r["side"] == HOLD
    print("OK precio pegado al VWAP -> HOLD (neutral)")


def test_vacio_no_rompe():
    assert vwap(None) is None
    assert vwap_signal(_df([]))["side"] == HOLD
    print("OK entradas vacías no rompen")


if __name__ == "__main__":
    test_vwap_promedio_sin_volumen()
    test_vwap_ponderado_por_volumen()
    test_precio_encima_es_call()
    test_precio_debajo_es_put()
    test_pegado_al_vwap_es_hold()
    test_vacio_no_rompe()
    print("\nTODOS OK — VWAP (nivel de referencia)")
