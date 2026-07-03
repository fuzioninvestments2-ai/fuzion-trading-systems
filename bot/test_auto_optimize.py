"""
bot/test_auto_optimize.py
=========================
Valida el auto-optimizador SIN red: acierto por temporalidad, la regla de ajuste
(sube/baja/neutra con topes) y la persistencia incremental por bot.
"""

from bot.history import HistoryRepository
from bot.signal_log import SignalTracker
from bot.auto_optimize import (TimeframeOptimizer, winrate_por_timeframe,
                               _nuevo_peso, PESO_INICIAL, PESO_MIN, PESO_MAX)


def _tracker():
    return SignalTracker(HistoryRepository(":memory:"))


def _sembrar(tr, timeframe, wins, losses, asset="EURUSD"):
    """Inserta señales YA resueltas con un resultado dado (para medir win-rate)."""
    with tr._lock:
        for _ in range(wins):
            tr.conn.execute(
                """INSERT INTO signals (asset,timeframe,direction,entry_price,
                   entry_ts,expiry_ts,result,resolved)
                   VALUES (?,?,?,1.0,0,0,'win',1)""", (asset, timeframe, "CALL"))
        for _ in range(losses):
            tr.conn.execute(
                """INSERT INTO signals (asset,timeframe,direction,entry_price,
                   entry_ts,expiry_ts,result,resolved)
                   VALUES (?,?,?,1.0,0,0,'loss',1)""", (asset, timeframe, "CALL"))
        tr.conn.commit()


def test_regla_ajuste_pura():
    assert _nuevo_peso(0.10, 0.70) == 0.15         # >65% sube
    assert _nuevo_peso(0.10, 0.40) == 0.05         # <45% baja
    assert _nuevo_peso(0.10, 0.55) == 0.10         # zona neutra: igual
    assert _nuevo_peso(0.29, 0.90) == PESO_MAX     # tope 0.30
    assert _nuevo_peso(0.04, 0.10) == PESO_MIN     # piso 0.02
    print("OK regla de ajuste (sube/baja/neutra, con topes)")


def test_winrate_por_timeframe():
    tr = _tracker()
    _sembrar(tr, "M5", wins=14, losses=6)          # 70%
    _sembrar(tr, "M1", wins=4, losses=16)          # 20%
    wr = winrate_por_timeframe(tr)
    assert abs(wr["M5"]["win_rate"] - 0.70) < 1e-9
    assert abs(wr["M1"]["win_rate"] - 0.20) < 1e-9
    print("OK acierto por temporalidad (M5=70%, M1=20%)")


def test_optimizar_sube_bueno_baja_malo():
    tr = _tracker()
    _sembrar(tr, "M5", wins=14, losses=6)          # 70% -> sube
    _sembrar(tr, "M1", wins=4, losses=16)          # 20% -> baja
    opt = TimeframeOptimizer(tr)
    cambios = opt.optimizar()
    assert cambios["M5"]["peso_despues"] == round(PESO_INICIAL + 0.05, 4)
    assert cambios["M1"]["peso_despues"] == round(PESO_INICIAL - 0.05, 4)
    # Persistió.
    pesos = opt.pesos("*")
    assert pesos["M5"] > pesos["M1"]
    print(f"OK optimiza: M5 sube a {pesos['M5']}, M1 baja a {pesos['M1']}")


def test_incremental_y_muestra_minima():
    tr = _tracker()
    _sembrar(tr, "M5", wins=14, losses=6)          # 70%
    _sembrar(tr, "M30", wins=4, losses=2)          # 67% pero solo 6 muestras
    opt = TimeframeOptimizer(tr)
    opt.optimizar()
    opt.optimizar()                                # dos rondas: incremental
    pesos = opt.pesos("*")
    assert pesos["M5"] == round(PESO_INICIAL + 0.10, 4)   # subió dos veces
    assert "M30" not in pesos                       # muestra < 10: no se toca
    print(f"OK incremental (M5={pesos['M5']}) y respeta muestra mínima (M30 fuera)")


def test_separado_por_activo():
    tr = _tracker()
    _sembrar(tr, "M5", 14, 6, asset="EURUSD")
    opt = TimeframeOptimizer(tr)
    opt.optimizar(asset="EURUSD")
    assert "M5" in opt.pesos("EURUSD") and "M5" not in opt.pesos("*")
    print("OK pesos separados por activo (y por bot, al usar BD distinta)")


if __name__ == "__main__":
    test_regla_ajuste_pura()
    test_winrate_por_timeframe()
    test_optimizar_sube_bueno_baja_malo()
    test_incremental_y_muestra_minima()
    test_separado_por_activo()
    print("\nTODOS OK — auto-optimización por temporalidad")
