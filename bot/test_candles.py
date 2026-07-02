"""
bot/test_candles.py
==================
Valida el CandleBuilder, en especial la vela EN FORMACIÓN (que el gráfico usa
para no ir una vela atrás). Sin red, determinista.
"""

from bot.candles import CandleBuilder


def test_cierra_vela_al_cambiar_intervalo():
    cb = CandleBuilder(60)                      # velas de 60s
    assert cb.add_tick(1.10, 0) is None         # abre vela del minuto 0
    assert cb.add_tick(1.11, 30_000) is None    # mismo minuto
    cerrada = cb.add_tick(1.12, 60_000)         # minuto 1 -> cierra la del 0
    assert cerrada is not None
    assert cerrada["open"] == 1.10 and cerrada["close"] == 1.11
    print("OK cierra la vela al cambiar de intervalo")


def test_forming_candle_refleja_el_minuto_en_curso():
    cb = CandleBuilder(60)
    cb.add_tick(1.10, 0)
    cb.add_tick(1.15, 20_000)                   # máximo del minuto
    cb.add_tick(1.08, 40_000)                   # mínimo del minuto
    f = cb.forming_candle()
    assert f is not None
    assert f["open"] == 1.10 and f["high"] == 1.15
    assert f["low"] == 1.08 and f["close"] == 1.08
    # No está entre las cerradas todavía.
    assert cb.closed_candles() == []
    print("OK la vela en formación refleja el minuto en curso")


def test_forming_candle_es_copia():
    cb = CandleBuilder(60)
    cb.add_tick(1.10, 0)
    f = cb.forming_candle()
    f["close"] = 999                            # modificar la copia...
    assert cb.forming_candle()["close"] == 1.10  # ...no afecta al builder
    print("OK forming_candle devuelve una copia (no muta el builder)")


def test_forming_candle_none_al_inicio():
    cb = CandleBuilder(60)
    assert cb.forming_candle() is None
    print("OK sin ticks, no hay vela en formación")


def test_include_forming_en_dataframe():
    cb = CandleBuilder(60)
    cb.add_tick(1.10, 0)
    cb.add_tick(1.12, 60_000)                   # cierra la del minuto 0, abre 1
    sin = cb.to_dataframe(include_forming=False)
    con = cb.to_dataframe(include_forming=True)
    assert len(con) == len(sin) + 1             # la de formación añade 1 fila
    print("OK include_forming añade la vela viva al DataFrame")


if __name__ == "__main__":
    test_cierra_vela_al_cambiar_intervalo()
    test_forming_candle_refleja_el_minuto_en_curso()
    test_forming_candle_es_copia()
    test_forming_candle_none_al_inicio()
    test_include_forming_en_dataframe()
    print("\nTODOS OK — CandleBuilder y vela en formación")
