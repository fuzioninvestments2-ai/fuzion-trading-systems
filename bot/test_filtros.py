"""
bot/test_filtros.py
===================
Valida los filtros obligatorios SIN red: payout (ambos), y noticias/sesión/spread
(solo real). Y el veredicto final (sinfonía + filtros).
"""

import numpy as np
import pandas as pd

from bot.filtros import evaluar_filtros, clasificar_sesion, veredicto_final
from bot import otc_system, real_system

TFS = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]


def _df(subiendo=True, n=260):
    close = pd.Series([100 + (i if subiendo else (n - i)) * 0.2 for i in range(n)],
                      dtype=float)
    return pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]),
                         "high": close + 0.15, "low": close - 0.15, "close": close})


def test_payout_bloquea_ambos():
    assert evaluar_filtros(otc_system, payout=70)["pasa"] is False   # <75
    assert evaluar_filtros(otc_system, payout=80)["pasa"] is True    # 75-85
    assert evaluar_filtros(otc_system, payout=88)["pasa"] is False   # peligroso
    print("OK payout: 70 bloquea, 80 pasa, 88 (peligroso) bloquea")


def test_noticias_solo_real():
    # OTC ignora noticias; real las bloquea.
    assert evaluar_filtros(otc_system, hay_noticia=True)["pasa"] is True
    r = evaluar_filtros(real_system, hay_noticia=True)
    assert r["pasa"] is False and "noticia" in r["fallos"][0]
    print("OK noticias solo bloquean en real (OTC 24/7 las ignora)")


def test_sesion_y_spread_solo_real():
    # Sesión a evitar (Asia 22h EST) bloquea en real.
    assert clasificar_sesion(22, real_system) == "evitar"
    assert clasificar_sesion(3, real_system) == "buena"      # London
    r = evaluar_filtros(real_system, hora_est=22)
    assert r["pasa"] is False
    # Spread > 2 pips bloquea.
    assert evaluar_filtros(real_system, spread=3.0)["pasa"] is False
    assert evaluar_filtros(real_system, spread=1.0)["pasa"] is True
    print("OK real: sesión Asia y spread>2 bloquean")


def test_veredicto_final_operar_y_bloqueo():
    frames = {tf: _df(subiendo=True) for tf in TFS}
    # Sin filtros que fallen -> OPERAR.
    ok = veredicto_final(frames, otc_system, payout=80)
    assert ok["veredicto"] == "OPERAR", ok
    # Payout malo -> el filtro tumba el OPERAR.
    bloq = veredicto_final(frames, otc_system, payout=70)
    assert bloq["veredicto"] == "NO OPERAR" and bloq["filtros"]["fallos"]
    print(f"OK veredicto final: alineado+payout ok = OPERAR; payout malo = NO OPERAR")


def test_real_noticia_tumba_operar():
    frames = {tf: _df(subiendo=True) for tf in TFS}
    r = veredicto_final(frames, real_system, payout=80, hay_noticia=True)
    assert r["veredicto"] == "NO OPERAR"
    print("OK real: aunque alinee, una noticia bloquea la entrada")


if __name__ == "__main__":
    test_payout_bloquea_ambos()
    test_noticias_solo_real()
    test_sesion_y_spread_solo_real()
    test_veredicto_final_operar_y_bloqueo()
    test_real_noticia_tumba_operar()
    print("\nTODOS OK — filtros obligatorios + veredicto final")
