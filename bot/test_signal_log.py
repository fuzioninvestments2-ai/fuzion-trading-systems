"""
bot/test_signal_log.py
=====================
Valida el registro y la resolución de señales (ciclo de aprendizaje real).
Sin red, determinista (timestamps fijos, no reloj real).
"""

from bot.history import HistoryRepository
from bot.signal_log import SignalTracker, CALL, PUT


def _repo_con_velas(asset="EURUSD_otc"):
    repo = HistoryRepository(":memory:")
    # Velas M1 con precio creciente: 100.0, 100.1, ... (ts en ms).
    velas = [{"timestamp": i * 60_000, "open": 100 + i * 0.1,
              "high": 100 + i * 0.1, "low": 100 + i * 0.1,
              "close": 100 + i * 0.1, "volume": 1} for i in range(20)]
    repo.record_many(asset, "M1", velas)
    return repo


def test_registra_solo_call_put():
    repo = _repo_con_velas()
    tr = SignalTracker(repo)
    assert tr.record("EURUSD_otc", "1m", CALL, 100.0, 0, 60) is not None
    # HOLD u otra cosa no se registra.
    assert tr.record("EURUSD_otc", "1m", "HOLD", 100.0, 0, 60) is None
    assert tr.stats()["pendientes"] == 1
    print("OK registra solo CALL/PUT (HOLD se ignora)")


def test_resuelve_call_ganadora():
    repo = _repo_con_velas()
    tr = SignalTracker(repo)
    # Entrada en ts=0 a 100.0, vence 60s después; el precio SUBE -> CALL gana.
    tr.record("EURUSD_otc", "1m", CALL, 100.0, 0, 60)
    resueltas = tr.resolve_pending(now_ts_ms=10 * 60_000)
    assert resueltas == 1
    s = tr.stats()
    assert s["wins"] == 1 and s["win_rate"] == 1.0
    print("OK resuelve CALL ganadora (precio subió)")


def test_resuelve_put_perdedora():
    repo = _repo_con_velas()
    tr = SignalTracker(repo)
    # PUT cuando el precio sube -> pierde.
    tr.record("EURUSD_otc", "1m", PUT, 100.0, 0, 60)
    tr.resolve_pending(now_ts_ms=10 * 60_000)
    s = tr.stats()
    assert s["losses"] == 1 and s["win_rate"] == 0.0
    print("OK resuelve PUT perdedora (precio subió)")


def test_no_resuelve_si_no_hay_vela_de_vencimiento():
    repo = _repo_con_velas()
    tr = SignalTracker(repo)
    # Vencimiento MUY en el futuro (más allá de las velas guardadas) -> pendiente.
    tr.record("EURUSD_otc", "1m", CALL, 100.0, 0, 999_999)
    n = tr.resolve_pending(now_ts_ms=10_000_000_000)
    assert n == 0 and tr.stats()["pendientes"] == 1
    print("OK no resuelve sin vela de vencimiento (queda pendiente)")


def test_win_rate_por_activo():
    repo = _repo_con_velas()
    tr = SignalTracker(repo)
    tr.record("EURUSD_otc", "1m", CALL, 100.0, 0, 60)     # gana
    tr.record("EURUSD_otc", "1m", PUT, 100.0, 0, 60)      # pierde
    tr.resolve_pending(now_ts_ms=10 * 60_000)
    s = tr.stats(asset="EURUSD_otc")
    assert s["decididas"] == 2 and s["win_rate"] == 0.5
    print(f"OK win-rate por activo = {s['win_rate']:.0%} ({s['decididas']} señales)")


if __name__ == "__main__":
    test_registra_solo_call_put()
    test_resuelve_call_ganadora()
    test_resuelve_put_perdedora()
    test_no_resuelve_si_no_hay_vela_de_vencimiento()
    test_win_rate_por_activo()
    print("\nTODOS OK — ciclo de aprendizaje real (señales registradas y resueltas)")
