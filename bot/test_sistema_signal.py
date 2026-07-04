"""
bot/test_sistema_signal.py
==========================
Valida el formateo de la señal del sistema del usuario SIN red.
"""

import numpy as np
import pandas as pd

from bot.sistema_signal import senal, lectura_extra
from bot import otc_system, real_system

TFS = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]


def _frames(subiendo=True, n=260):
    def df():
        c = pd.Series([100 + (i if subiendo else (n - i)) * 0.2 for i in range(n)],
                      dtype=float)
        return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                             "high": c + 0.15, "low": c - 0.15, "close": c})
    return {tf: df() for tf in TFS}


def test_senal_operar_tiene_lo_esencial():
    texto, res = senal(_frames(True), otc_system, "Fuzion POption OTC",
                       "EUR/USD OTC", "M5", payout=82)
    assert "OPERAR" in texto and "Fuzion POption OTC" in texto
    assert "EMA200 1H" in texto and "Alineación" in texto
    assert res["veredicto"] == "OPERAR"
    print("OK señal OPERAR con dirección, alineación, filtros y panel")


def test_lectura_extra_tiene_hora_de_entrada():
    """El bloque de lectura debe traer la HORA DE ENTRADA (lo que pidió el trader
    para operar) más VWAP, techo/piso, patrones e historial."""
    old = {"patrones": ["Doji (indecisión)"],
           "vwap": {"vwap": 0.708, "side": "PUT", "dist_pct": -0.02},
           "levels": {"resistencias": [0.70890], "soportes": [0.70770]},
           "m1_count": 420}
    bloque = lectura_extra(300, old)          # 300s hasta la próxima vela
    assert "Entra a las" in bloque and "300s" in bloque     # hora de entrada
    assert "VWAP" in bloque and "Techo" in bloque and "Patrones" in bloque
    assert "420 velas" in bloque
    print("OK lectura_extra: hora de entrada + VWAP + techo/piso + patrones")


def test_lectura_extra_entra_ya_si_falta_poco():
    bloque = lectura_extra(3, None)           # 3s -> ya
    assert "ENTRA YA" in bloque
    print("OK lectura_extra: avisa '¡ENTRA YA!' cuando faltan <=5s")


def test_senal_con_extras_los_incluye():
    extras = lectura_extra(120, {"m1_count": 300})
    texto, _ = senal(_frames(True), otc_system, "Fuzion POption OTC",
                     "EUR/USD OTC", "M5", payout=82, extras=extras)
    assert "Entra a las" in texto and "300 velas" in texto
    print("OK la tarjeta del sistema incluye el bloque de lectura (hora entrada)")


def test_senal_sin_extras_sigue_igual():
    texto, _ = senal(_frames(True), otc_system, "Fuzion POption OTC",
                     "EUR/USD OTC", "M5", payout=82)
    assert "Entra a las" not in texto        # sin extras: tarjeta simple, sin romper
    print("OK sin extras la tarjeta sigue funcionando (compatibilidad)")


def test_senal_bloqueada_por_payout():
    texto, res = senal(_frames(True), otc_system, "Fuzion POption OTC",
                       "EUR/USD OTC", "M5", payout=70)
    assert "NO OPERAR" in texto and res["veredicto"] == "NO OPERAR"
    assert "payout" in texto.lower()
    print("OK payout malo -> la señal muestra NO OPERAR con el motivo")


def test_senal_real_bloqueada_por_noticia():
    texto, res = senal(_frames(True), real_system, "Fuzion POption FX",
                       "EUR/USD", "M5", payout=82, hay_noticia=True)
    assert res["veredicto"] == "NO OPERAR" and "noticia" in texto.lower()
    print("OK real: noticia -> NO OPERAR en la señal")


if __name__ == "__main__":
    test_senal_operar_tiene_lo_esencial()
    test_lectura_extra_tiene_hora_de_entrada()
    test_lectura_extra_entra_ya_si_falta_poco()
    test_senal_con_extras_los_incluye()
    test_senal_sin_extras_sigue_igual()
    test_senal_bloqueada_por_payout()
    test_senal_real_bloqueada_por_noticia()
    print("\nTODOS OK — formateo de señal del sistema del usuario")
