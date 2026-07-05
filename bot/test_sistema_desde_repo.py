"""
bot/test_sistema_desde_repo.py
==============================
Valida que la señal del sistema se construya desde el HISTORIAL (repo) SIN red:
con velas alcistas en las 12 temporalidades -> OPERAR CALL; con poca historia ->
NO OPERAR (honesto, no inventa).
"""

from bot.history import HistoryRepository
from bot.sistema_signal import frames_desde_repo, senal_desde_repo
from bot import otc_system, real_system


def _sembrar(repo, asset, tf, n=260, subiendo=True):
    import time
    key = "M1" if tf == 60 else f"tf{tf}"
    # Velas FRESCAS: la última cae ~ahora, para pasar el filtro de frescura (en OTC
    # solo cuenta lo reciente; el historial viejo no aplica al mercado de ahora).
    base = int(time.time()) - n * int(tf)
    velas = []
    for i in range(n):
        c = 100 + (i if subiendo else (n - i)) * 0.2
        velas.append({"timestamp": (base + i * int(tf)) * 1000, "open": c,
                      "high": c + 0.15, "low": c - 0.15, "close": c, "volume": 1})
    repo.record_many(asset, key, velas)


def test_frames_desde_repo():
    repo = HistoryRepository(":memory:")
    for tf in otc_system.TIMEFRAMES_OTC:
        _sembrar(repo, "EURUSD_otc", tf)
    frames = frames_desde_repo(repo, otc_system, "EURUSD_otc")
    assert len(frames) == 12
    print(f"OK arma las 12 temporalidades desde el repo")


def test_senal_operar_desde_repo():
    repo = HistoryRepository(":memory:")
    for tf in otc_system.TIMEFRAMES_OTC:
        _sembrar(repo, "EURUSD_otc", tf, subiendo=True)
    texto, res = senal_desde_repo(repo, otc_system, "Fuzion POption OTC",
                                  "EURUSD_otc", "EUR/USD OTC", "M5", payout=82)
    assert res["veredicto"] == "OPERAR" and "CALL" in texto
    print("OK historial alcista completo -> OPERAR CALL")


def test_poca_historia_no_opera():
    repo = HistoryRepository(":memory:")
    # Solo unas pocas velas (sin 1H con EMA200) -> no hay dirección absoluta.
    for tf in (5, 10, 15):
        _sembrar(repo, "EURUSD_otc", tf, n=8)
    texto, res = senal_desde_repo(repo, otc_system, "Fuzion POption OTC",
                                  "EURUSD_otc", "EUR/USD OTC", "M5", payout=82)
    assert res["veredicto"] == "NO OPERAR"
    print("OK poca historia (sin 1H) -> NO OPERAR (honesto, no inventa)")


def test_real_no_crashea_y_filtra_sesion():
    # Regresión: el sistema REAL usaba TIMEFRAMES_OTC (inexistente) y crasheaba.
    repo = HistoryRepository(":memory:")
    for tf in real_system.TIMEFRAMES:
        _sembrar(repo, "EURUSD", tf, subiendo=True)
    # Sesión buena (London, 3h EST) -> puede operar.
    _, res = senal_desde_repo(repo, real_system, "Fuzion POption FX", "EURUSD",
                              "EUR/USD", "M5", payout=82, hora_est=3)
    assert res["veredicto"] in ("OPERAR", "NO OPERAR")   # no crashea
    # Sesión a evitar (Asia, 22h EST) -> bloquea aunque alinee.
    _, res2 = senal_desde_repo(repo, real_system, "Fuzion POption FX", "EURUSD",
                               "EUR/USD", "M5", payout=82, hora_est=22)
    if res["veredicto"] == "OPERAR":
        assert res2["veredicto"] == "NO OPERAR"
    print("OK sistema REAL no crashea y aplica el filtro de sesión")


if __name__ == "__main__":
    test_frames_desde_repo()
    test_senal_operar_desde_repo()
    test_poca_historia_no_opera()
    test_real_no_crashea_y_filtra_sesion()
    print("\nTODOS OK — señal del sistema construida desde el historial")
