"""
bot/test_sistema_signal.py
==========================
Valida el formateo de la señal del sistema del usuario SIN red.
"""

import numpy as np
import pandas as pd

from bot.sistema_signal import senal
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
    test_senal_bloqueada_por_payout()
    test_senal_real_bloqueada_por_noticia()
    print("\nTODOS OK — formateo de señal del sistema del usuario")
