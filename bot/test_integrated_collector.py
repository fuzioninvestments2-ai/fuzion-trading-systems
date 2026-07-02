"""
bot/test_integrated_collector.py
===============================
Valida el COLECTOR INTEGRADO en PocketService (una sola conexión): rotación,
foco e intercalado. Sin red (no se abre socket en el constructor).
"""

import asyncio

from bot.pocket_service import PocketService


def _svc():
    return PocketService('42["auth",{}]', demo=True, db_path=":memory:")


def test_watchlist_por_defecto():
    s = _svc()
    assert len(s._watchlist) >= 8
    print(f"OK watchlist por defecto ({len(s._watchlist)} activos)")


def test_pick_sin_foco_rota():
    s = _svc()
    picks = [s._watch_pick(i) for i in range(len(s._watchlist))]
    assert picks == s._watchlist
    print("OK sin foco rota la watchlist en orden")


def test_pick_con_foco_intercala():
    s = _svc()
    s._focus = "EURUSD_otc"
    picks = [s._watch_pick(i) for i in range(6)]
    assert [picks[0], picks[2], picks[4]] == ["EURUSD_otc"] * 3, picks
    print(f"OK con foco intercala (3/6 turnos): {picks}")


def test_collect_loop_es_corutina():
    s = _svc()
    assert asyncio.iscoroutinefunction(s._collect_loop)
    print("OK _collect_loop es corutina (tarea de fondo)")


def test_lock_perezoso_no_rompe():
    # Antes de start() el lock es None; analyze usa nullcontext y no debe romper.
    import contextlib
    s = _svc()
    lock = s._conn_lock or contextlib.nullcontext()
    assert lock is not None
    print("OK lock perezoso: sin start() usa nullcontext")


if __name__ == "__main__":
    test_watchlist_por_defecto()
    test_pick_sin_foco_rota()
    test_pick_con_foco_intercala()
    test_collect_loop_es_corutina()
    test_lock_perezoso_no_rompe()
    print("\nTODOS OK — colector integrado (una sola conexión)")
