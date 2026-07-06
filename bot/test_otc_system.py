"""
bot/test_otc_system.py
======================
Valida que la CONFIGURACIÓN del sistema OTC del usuario esté fielmente encodeada
(documentar = ejecutar). Sin red.
"""

from bot import otc_system as s


def test_diez_indicadores_con_su_config():
    assert len(s.INDICADORES_OTC) == 10
    # Parámetros exactos que pidió el usuario.
    assert s.indicador("ema8")["periodo"] == 8
    assert s.indicador("ema200")["periodo"] == 200
    st = s.indicador("stochastic")
    assert (st["k"], st["d"], st["suavizado"]) == (5, 3, 3)
    bb = s.indicador("bollinger")
    assert (bb["periodo"], bb["desv"]) == (14, 1.02)
    assert s.indicador("donchian")["periodo"] == 20
    assert s.indicador("rsi")["periodo"] == 5
    mc = s.indicador("macd")
    assert (mc["fast"], mc["slow"], mc["signal"]) == (12, 26, 9)
    assert s.indicador("soporte_resistencia")["lookback"] == 20
    print("OK 10 indicadores con la config exacta (EMA/Stoch 5,3,3/BB 14,1.02/...)")


def test_doce_timeframes():
    assert s.TIMEFRAMES_OTC == [5, 10, 15, 30, 60, 120, 180, 300, 600, 900,
                                1800, 3600]
    assert len(s.TIMEFRAMES_OTC) == 12
    print("OK 12 temporalidades 5s..1H")


def test_pesos_alineacion_suman_100():
    assert sum(s.PESOS_ALINEACION.values()) == 100
    assert s.peso_alineacion(3600) == 30        # 1H manda
    assert s.peso_alineacion(5) == 0            # 5s lee pero no pesa
    assert s.ALINEACION_MINIMA == 7
    print("OK pesos de alineación suman 100; 1H=30%, mínimo 7/12")


def test_clasificar_payout():
    assert s.clasificar_payout(70) == "no_operar"
    assert s.clasificar_payout(75) == "bueno"
    assert s.clasificar_payout(85) == "bueno"
    assert s.clasificar_payout(88) == "aceptable"     # 85+ operable con aviso (trader opera a 92%)
    assert s.clasificar_payout(92) == "aceptable"
    assert s.clasificar_payout(None) == "no_operar"
    print("OK payout: <75 no operar, 75-85 bueno, 85+ aceptable (opera a 92%)")


def test_filtros_y_ciclo():
    assert s.NOTICIAS_ANTES_MIN == 15 and s.NOTICIAS_DESPUES_MIN == 30
    assert s.CICLO_MERCADO == ["compresión", "acumulación", "saturación",
                               "reversión"]
    assert any("London" in n for n, _, _ in s.SESIONES_BUENAS)
    print("OK noticias 15/30 min, ciclo y sesiones encodeados")


if __name__ == "__main__":
    test_diez_indicadores_con_su_config()
    test_doce_timeframes()
    test_pesos_alineacion_suman_100()
    test_clasificar_payout()
    test_filtros_y_ciclo()
    print("\nTODOS OK — sistema OTC (config del usuario) documentado = ejecutable")
