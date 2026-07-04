"""
bot/test_real_system.py
=======================
Valida la config del sistema MERCADO REAL: comparte la base del OTC y difiere en
alineación (8/12), noticias (también durante), spread y sesiones. Sin red.
"""

from bot import real_system as r
from bot import otc_system as o


def test_base_identica_al_otc():
    # Mismos 10 indicadores, mismas 12 temporalidades, mismos pesos.
    assert r.INDICADORES_REAL is o.INDICADORES_OTC
    assert r.TIMEFRAMES_REAL == o.TIMEFRAMES_OTC
    assert r.PESOS_ALINEACION == o.PESOS_ALINEACION
    assert r.indicador("rsi")["periodo"] == 5
    assert r.indicador("bollinger")["desv"] == 1.02
    print("OK real comparte la base del OTC (10 indicadores, 12 tiempos, pesos)")


def test_alineacion_mas_estricta():
    assert r.ALINEACION_MINIMA == 8            # más estricto
    assert r.ALINEACION_MINIMA > o.ALINEACION_MINIMA   # OTC = 7
    print("OK alineación real más estricta (8/12 vs 7/12 OTC)")


def test_noticias_criticas():
    assert r.NOTICIAS_DURANTE is True          # OTC no bloquea durante; real sí
    assert r.NOTICIAS_ANTES_MIN == 15 and r.NOTICIAS_DESPUES_MIN == 30
    assert "ForexFactory" in r.CALENDARIOS
    print("OK noticias factor #1: antes, DURANTE y después")


def test_spread():
    assert r.SPREAD_MAX_PIPS == 2.0
    assert r.spread_ok(1.5) is True
    assert r.spread_ok(3.0) is False
    assert r.spread_ok(None) is True           # sin dato no bloquea
    print("OK filtro de spread (<=2 pips; None no bloquea)")


def test_payout_y_sesiones_compartidos():
    assert r.clasificar_payout(70) == "no_operar"
    assert r.clasificar_payout(80) == "bueno"
    assert any("London" in n for n, _, _ in r.SESIONES_BUENAS)
    assert any("Asia" in n for n, _, _ in r.SESIONES_EVITAR)
    print("OK payout compartido y sesiones (London/NY buenas, Asia/NY PM evitar)")


if __name__ == "__main__":
    test_base_identica_al_otc()
    test_alineacion_mas_estricta()
    test_noticias_criticas()
    test_spread()
    test_payout_y_sesiones_compartidos()
    print("\nTODOS OK — sistema MERCADO REAL (config del usuario)")
