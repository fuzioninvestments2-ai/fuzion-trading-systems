"""
bot/test_robot_reversion.py
===========================
Valida sin red las partes puras del lanzador: extracción del chat_id de los updates,
la lista de pares fuertes, y que el flujo tick->vela->señal encola un aviso (con repo
temporal e horario forzado abierto). La conexión real y el envío a Telegram no se
prueban aquí (necesitan internet).
"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.robot_reversion import RobotReversion, _chat_de_updates, PARES_FUERTES
from bot.history import HistoryRepository
from bot.profiles import get_profile


def _update(chat_id):
    chat = types.SimpleNamespace(id=chat_id)
    return types.SimpleNamespace(effective_chat=chat, message=None)


def test_chat_de_updates_toma_el_ultimo():
    ups = [_update(111), _update(222)]
    assert _chat_de_updates(ups) == "222"                  # el más reciente
    assert _chat_de_updates([]) is None
    assert _chat_de_updates(None) is None


def test_pares_fuertes_son_cruces():
    assert "EURCHF" in PARES_FUERTES and "AUDNZD" in PARES_FUERTES
    assert len(PARES_FUERTES) == 7


def _robot_tmp(tmpdb):
    return RobotReversion(
        get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
        tabla={"EURCHF": [[5, 70.0]]}, repo=HistoryRepository(tmpdb),
        is_open_fn=lambda p: True)                          # horario forzado abierto


def test_tick_a_senal_encola():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        # Cierra varias velas M1; entre dos consecutivas hay un salto de 10 pips.
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() >= 1                         # se generó al menos un aviso
        s = r._cola.get_nowait()
        assert s["par"] == "EURCHF" and s["direccion"] == "PUT"


def test_mercado_cerrado_no_encola():
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
            tabla={"EURCHF": [[5, 70.0]]}, repo=HistoryRepository(os.path.join(d, "h.db")),
            is_open_fn=lambda p: False)                     # cerrado
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == 0                         # cerrado -> nada


def test_on_history_guarda_velas_ohlc():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        payload = {"asset": "EURCHF", "period": 300, "candles": [
            {"time": 1700000000, "open": 1.08, "high": 1.081, "low": 1.079, "close": 1.0805},
            {"time": 1700000300, "open": 1.0805, "high": 1.0812, "low": 1.0801, "close": 1.081},
        ]}
        r._on_history(payload)
        df = r.repo.get_recent("EURCHF", "tf300", 10)
        assert df is not None and len(df) == 2          # guardó las 2 velas de 5m


def test_on_history_guarda_ticks_como_m1():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        # Ticks en dos minutos distintos -> al menos una vela M1 cerrada.
        hist = [[1700000000, 1.0800], [1700000030, 1.0802],
                [1700000060, 1.0805], [1700000120, 1.0808]]
        r._on_history({"asset": "EURCHF", "period": 60, "history": hist})
        df = r.repo.get_recent("EURCHF", "M1", 10)
        assert df is not None and len(df) >= 1


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
