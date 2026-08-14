"""
tests/test_backtest_cuantico.py (fuzion_fx)
===========================================
Valida la MECANICA del backtest cuantico (no la rentabilidad):
 - _ventana NO mira el futuro (solo velas con ts <= t).
 - _leer_csv parsea el formato interno (timestamp ms, ohlcv).
 - backtest() corre sobre series sinteticas y arma el reporte con break-even
   correcto y win-rate en rango.
SIN red, SIN datos OTC (serie sintetica; OTC no representa el mercado real).
"""

from __future__ import annotations

import gzip
import os
import sys
import tempfile

import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import backtest_cuantico as bt                    # noqa: E402


def _serie(direccion, n=400, tf=60, t0=1_700_000_000):
    """Serie sintetica con tendencia (para que el motor tenga algo que votar)."""
    rng = np.random.RandomState(1)
    drift = np.linspace(0.0, direccion * 0.02, n)
    ruido = np.cumsum(rng.normal(0, 0.0003, n))
    ruido -= np.linspace(0.0, ruido[-1], n)
    close = 1.1000 + drift + 0.4 * ruido
    o = np.concatenate([[close[0]], close[:-1]])
    return {"ts": np.arange(t0, t0 + n * tf, tf, dtype=np.int64)[:n],
            "open": o, "high": np.maximum(o, close) * 1.0002,
            "low": np.minimum(o, close) * 0.9998, "close": close}


def test_ventana_no_mira_futuro() -> None:
    s = _serie(+1, n=200, tf=60)
    t = int(s["ts"][120])                                # corte en la vela 120
    v = bt._ventana(s, t, n=150)
    assert v is not None
    # La ultima vela de la ventana debe ser exactamente la de t (ninguna posterior).
    assert v["close"][-1] == s["close"][120]
    assert len(v["close"]) == 121                        # velas 0..120 inclusive


def test_ventana_exige_minimo() -> None:
    s = _serie(+1, n=200, tf=60)
    t = int(s["ts"][10])                                 # solo 11 velas <= t
    assert bt._ventana(s, t, n=150) is None              # < MIN_VELAS -> None


def test_leer_csv_formato_interno() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False)
    tmp.close()
    try:
        with gzip.open(tmp.name, "wt") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("1700000000000,1.1,1.2,1.0,1.15,10\n")
            f.write("1700000060000,1.15,1.25,1.1,1.2,12\n")
        s = bt._leer_csv(tmp.name)
        assert s is not None
        assert s["ts"][0] == 1_700_000_000               # ms -> s
        assert s["close"][-1] == 1.2
    finally:
        os.unlink(tmp.name)


def test_backtest_arma_reporte(monkeypatch) -> None:
    # Monkeypatch del cargador: series sinteticas alcistas en 4 tiempos.
    series = {60: _serie(+1, n=400, tf=60), 120: _serie(+1, n=250, tf=120),
              180: _serie(+1, n=200, tf=180), 300: _serie(+1, n=150, tf=300)}
    monkeypatch.setattr(bt, "cargar", lambda par, tfs, permitir_otc: series)
    rep = bt.backtest("TEST", [60, 120, 180, 300], pago=85.0, max_barras=300)
    assert "error" not in rep
    # Break-even de pago 85%: 100/(1+0.85) = 54.05%.
    assert abs(rep["break_even"] - 54.05405) < 0.01
    assert 0.0 <= rep["win_rate"] <= 100.0
    assert rep["operaciones"] + rep["ties"] >= 0


def test_backtest_sin_base_devuelve_error(monkeypatch) -> None:
    # Sin timeframe 60 (base) -> error claro, no crash.
    monkeypatch.setattr(bt, "cargar", lambda par, tfs, permitir_otc: {120: _serie(+1)})
    rep = bt.backtest("TEST", [120], pago=85.0)
    assert "error" in rep


# ---- runner sin pytest (compat con la suite del proyecto) -------------------
class _MP:
    def __init__(self): self._orig = []
    def setattr(self, obj, name, val):
        self._orig.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)
    def undo(self):
        for obj, name, val in reversed(self._orig):
            setattr(obj, name, val)


def _run_all() -> None:
    test_ventana_no_mira_futuro()
    print("  OK  test_ventana_no_mira_futuro")
    test_ventana_exige_minimo()
    print("  OK  test_ventana_exige_minimo")
    test_leer_csv_formato_interno()
    print("  OK  test_leer_csv_formato_interno")
    for t in (test_backtest_arma_reporte, test_backtest_sin_base_devuelve_error):
        mp = _MP()
        try:
            t(mp)
            print(f"  OK  {t.__name__}")
        finally:
            mp.undo()
    print("5 tests OK (sin red, sin OTC)")


if __name__ == "__main__":
    _run_all()
