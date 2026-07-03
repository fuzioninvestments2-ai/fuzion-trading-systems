"""
bot/test_history_backfill.py
===========================
Valida el manejo del historial: NO borra el buffer acumulado al cambiar de
activo, y guarda las velas al PERIODO recibido (profundidad de tiempos largos).
Sin red, determinista.
"""

from bot.pocket_service import PocketService


def _svc():
    return PocketService('42["auth",{}]', demo=True, db_path=":memory:")


def test_on_history_no_borra_buffer_acumulado():
    s = _svc()
    a = "CHFJPY_otc"
    for i in range(150):
        s._on_tick(a, 1000.0 + i, 190.0 + 0.001 * i)
    antes = len(s._ticks[a])
    # Llega historial M1 (como al re-suscribir): NO debe pisar lo acumulado.
    s._on_history({"asset": a, "period": 60,
                   "history": [[500.0 + i, 190.0] for i in range(15)]})
    assert len(s._ticks[a]) >= antes, "el buffer acumulado se borró"
    print(f"OK el buffer acumulado se conserva ({len(s._ticks[a])} ticks)")


def test_on_history_guarda_por_periodo():
    s = _svc()
    a = "CHFJPY_otc"
    # Historial M5 (period 300) -> se guarda bajo 'tf300'.
    s._on_history({"asset": a, "period": 300,
                   "history": [[i * 300.0, 190.0 + 0.01 * i] for i in range(40)]})
    assert s.repo.count(a, "tf300") > 0
    # Y no lo mezcla con M1.
    assert s.repo.count(a, "M1") == 0
    print(f"OK historial M5 guardado como tf300 ({s.repo.count(a, 'tf300')} velas)")


def test_on_history_ignora_vacio():
    s = _svc()
    s._on_history({"asset": "X_otc", "period": 60, "history": []})
    s._on_history({"asset": "X_otc"})
    s._on_history(None)
    print("OK historial vacío/none no rompe")


def test_request_history_es_corutina():
    import asyncio
    s = _svc()
    assert asyncio.iscoroutinefunction(s.client.request_history)
    print("OK request_history es corutina (reutiliza changeSymbol)")


if __name__ == "__main__":
    test_on_history_no_borra_buffer_acumulado()
    test_on_history_guarda_por_periodo()
    test_on_history_ignora_vacio()
    test_request_history_es_corutina()
    print("\nTODOS OK — historial: sin borrar buffer + profundidad por periodo")
