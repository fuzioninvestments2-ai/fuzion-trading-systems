"""
bot/test_sistema_desde_repo.py
==============================
Valida que la señal del sistema se construya desde el HISTORIAL (repo) SIN red:
con velas alcistas en las 12 temporalidades -> OPERAR CALL; con poca historia ->
NO OPERAR (honesto, no inventa).
"""

from bot.history import HistoryRepository
from bot.sistema_signal import frames_desde_repo, senal_desde_repo
from bot import otc_system


def _sembrar(repo, asset, tf, n=260, subiendo=True):
    key = "M1" if tf == 60 else f"tf{tf}"
    velas = []
    for i in range(n):
        c = 100 + (i if subiendo else (n - i)) * 0.2
        velas.append({"timestamp": i * tf * 1000, "open": c, "high": c + 0.15,
                      "low": c - 0.15, "close": c, "volume": 1})
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


if __name__ == "__main__":
    test_frames_desde_repo()
    test_senal_operar_desde_repo()
    test_poca_historia_no_opera()
    print("\nTODOS OK — señal del sistema construida desde el historial")
