"""
bot/test_candle_patterns.py
==========================
Valida la detección de patrones de vela. Sin red, determinista.
"""

import pandas as pd

from bot.candle_patterns import detect_patterns, CALL, PUT


def _df(velas):
    """velas: lista de (o,h,l,c)."""
    return pd.DataFrame(velas, columns=["open", "high", "low", "close"])


def test_doji_indecision():
    # Cuerpo diminuto, mechas a ambos lados -> doji.
    df = _df([(100, 101, 99, 100.02)])
    r = detect_patterns(df)
    assert r["indecision"] is True
    assert r["bias"] is None
    assert any("Doji" in p for p in r["patrones"])
    print("OK doji -> indecisión, bias None")


def test_martillo_call():
    # Cuerpo pequeño arriba, mecha inferior larga -> martillo (alza).
    df = _df([(100.0, 100.2, 98.0, 100.1)])
    r = detect_patterns(df)
    assert any("Martillo" in p for p in r["patrones"])
    assert r["bias"] == CALL
    print("OK martillo -> CALL")


def test_estrella_fugaz_put():
    # Cuerpo pequeño abajo, mecha superior larga -> estrella fugaz (baja).
    df = _df([(100.0, 102.0, 99.9, 100.0)])
    r = detect_patterns(df)
    assert any("Estrella" in p for p in r["patrones"])
    assert r["bias"] == PUT
    print("OK estrella fugaz -> PUT")


def test_marubozu_alcista():
    # Cuerpo que ocupa casi todo el rango, cierre > apertura -> marubozu alcista.
    df = _df([(100.0, 101.0, 100.0, 100.98)])
    r = detect_patterns(df)
    assert any("Marubozu alcista" in p for p in r["patrones"])
    assert r["bias"] == CALL
    print("OK marubozu alcista -> CALL")


def test_envolvente_alcista():
    # Vela previa bajista pequeña; actual alcista que la envuelve -> reversión ↑.
    df = _df([(100.0, 100.3, 99.7, 99.8),      # bajista
              (99.7, 100.6, 99.6, 100.5)])     # alcista envolvente
    r = detect_patterns(df)
    assert any("Envolvente alcista" in p for p in r["patrones"])
    assert r["bias"] == CALL
    print("OK envolvente alcista -> CALL")


def test_envolvente_bajista():
    df = _df([(100.0, 100.3, 99.8, 100.2),     # alcista
              (100.3, 100.4, 99.5, 99.6)])     # bajista envolvente
    r = detect_patterns(df)
    assert any("Envolvente bajista" in p for p in r["patrones"])
    assert r["bias"] == PUT
    print("OK envolvente bajista -> PUT")


def test_vacio_no_rompe():
    assert detect_patterns(None)["bias"] is None
    assert detect_patterns(_df([]))["patrones"] == []
    print("OK entradas vacías no rompen")


if __name__ == "__main__":
    test_doji_indecision()
    test_martillo_call()
    test_estrella_fugaz_put()
    test_marubozu_alcista()
    test_envolvente_alcista()
    test_envolvente_bajista()
    test_vacio_no_rompe()
    print("\nTODOS OK — patrones de vela")
