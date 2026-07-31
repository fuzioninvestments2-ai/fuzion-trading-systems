"""
bot/test_simulacion.py
======================
Valida sin red el forward-test interno: sobre una serie con reversión que PERSISTE dos
velas (pico arriba y luego baja), entrando en el borde m+2, las señales PUT ganan; una
serie sin reversión no deja señales ganadoras.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.simulacion import resamplear, simular


def _serie(n):
    # Período 4: 1.1000, 1.1012 (pico +12), 1.1006 (-6), 1.1000 (-6). La reversión tras el
    # pico persiste dos velas, así que entrando UNA vela después (borde m+2) el PUT gana.
    patron = [1.1000, 1.1012, 1.1006, 1.1000]
    closes = [patron[i % 4] for i in range(n)]
    ts = [1_700_000_000_000 + i * 60_000 for i in range(n)]   # M1 adyacente
    return ts, closes


def test_resamplear_por_tiempo():
    ts = [0, 30_000, 60_000, 90_000]          # dos bloques de 1m
    closes = [1.0, 1.1, 1.2, 1.3]
    inicios, bc = resamplear(ts, closes, 1)
    assert inicios == [0, 60_000]             # dos velas de 1m
    assert bc == [1.1, 1.3]                    # último cierre de cada bloque


def test_reversion_persistente_gana():
    ts, closes = _serie(120)
    tabla = {"EURUSD": {"1": [[8, 70.0]]}}     # solo el pico de +12 cuenta (>=8)
    r = simular(ts, closes, "EURUSD", 1, tabla, payout=85.0,
                con_tendencia=False, con_riesgo=False)
    assert r["señales"] > 0                     # hubo operaciones
    assert r["win_rate"] >= 90                  # el PUT tras el pico se devuelve -> gana


def test_sin_reversion_no_gana():
    # Tendencia monótona: no hay reversión -> el PUT/CALL contra el movimiento pierde.
    ts = [1_700_000_000_000 + i * 60_000 for i in range(120)]
    closes = [1.1000 + 0.0002 * i for i in range(120)]        # sube siempre
    tabla = {"EURUSD": {"1": [[4, 70.0]]}}
    r = simular(ts, closes, "EURUSD", 1, tabla, payout=85.0,
                con_tendencia=False, con_riesgo=False)
    # O no hay señales, o su acierto no supera el equilibrio (no hay borde real aquí).
    assert r["win_rate"] is None or r["win_rate"] < 55


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
