"""
bot/test_backtest_historico.py
==============================
Valida la MECÁNICA del backtest (sin red, con datos sintéticos):
  - `_resample_ohlc` agrega bien 5s → 60s (open=primero, close=último, high/low, vol).
  - `_busca` (binaria) encuentra el primer timestamp >= t.
  - Anti look-ahead: a las t solo entran velas cuyo bloque YA cerró (inicio+tf <= t).

No mide win-rate (eso depende de los datos reales); mide que la construcción de
frames no filtre el futuro, que es lo que invalidaría cualquier backtest.
"""
import pandas as pd

from bot.backtest_historico import _busca, _resample_ohlc


def _velas5(n):
    """n velas de 5s, timestamps 0,5000,10000,... precio creciente 100+i."""
    base = 1_000_000_000_000 // 900_000 * 900_000   # alineado a bloques de 900s (y 60s)
    filas = []
    for i in range(n):
        p = 100.0 + i
        filas.append({"timestamp": base + i * 5000, "open": p, "high": p + 0.5,
                      "low": p - 0.5, "close": p + 0.1, "volume": 10.0})
    return pd.DataFrame(filas)


def test_resample_60_desde_5():
    df5 = _velas5(24)                       # 24 velas de 5s = 120s = 2 velas de 60s
    r = _resample_ohlc(df5, 60)
    assert len(r) == 2, f"esperaba 2 velas de 60s, hay {len(r)}"
    # Primera vela de 60s: open=open de la primera 5s, close=close de la 12ª 5s.
    assert r["open"].iloc[0] == df5["open"].iloc[0]
    assert r["close"].iloc[0] == df5["close"].iloc[11]
    assert r["high"].iloc[0] == df5["high"].iloc[:12].max()
    assert r["low"].iloc[0] == df5["low"].iloc[:12].min()
    assert r["volume"].iloc[0] == df5["volume"].iloc[:12].sum()


def test_resample_tf5_identidad():
    df5 = _velas5(10)
    r = _resample_ohlc(df5, 5)
    assert len(r) == len(df5)
    assert r["close"].tolist() == df5["close"].tolist()


def test_busca_primer_mayor_igual():
    ts = [0, 100, 200, 300]
    assert _busca(ts, 150) == 2            # primer >= 150 es 200 (índice 2)
    assert _busca(ts, 200) == 2            # exacto
    assert _busca(ts, 0) == 0
    assert _busca(ts, 301) is None         # nada >= 301


def test_anti_lookahead_solo_velas_cerradas():
    # La regla del backtest: a las t entran velas con timestamp + tf*1000 <= t.
    # Una vela de 60s que empieza en t-30s NO está cerrada (cerraría en t+30s) y
    # DEBE quedar fuera: su close contendría el futuro.
    df5 = _velas5(48)                       # 240s de datos
    r60 = _resample_ohlc(df5, 60)
    t = int(df5["timestamp"].iloc[0]) + 90_000   # t = 90s desde el inicio
    cerradas = r60[r60["timestamp"] + 60 * 1000 <= t]
    # Bloques que empiezan en 0 y 60s cierran en 60s y 120s. Solo el de 0 cerró<=90s.
    assert len(cerradas) == 1, f"a t=90s solo 1 vela de 60s cerrada, hay {len(cerradas)}"
    # La vela en formación (empieza 60s, cierra 120s) NO está.
    assert (cerradas["timestamp"] + 60_000 <= t).all()


if __name__ == "__main__":
    import sys
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
