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

from bot.robot_reversion import (RobotReversion, _chat_de_updates, PARES_FUERTES,
                                 ACTIVOS_PO)
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


def test_pares_fuertes_solo_los_de_po():
    assert "EURCHF" in PARES_FUERTES
    # PO real no ofrece NZD ni USDJPY: no deben estar.
    for prohibido in ("AUDNZD", "NZDUSD", "NZDJPY", "USDJPY"):
        assert prohibido not in PARES_FUERTES and prohibido not in ACTIVOS_PO
    # Todos los fuertes deben estar en la lista de activos de PO.
    assert all(p in ACTIVOS_PO for p in PARES_FUERTES)


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
        assert s.get("hora_entrada") and s.get("hora_vence")   # trae hora de entrada
        assert "HORA DE ENTRADA" in s["tarjeta"]
        assert "VENCE" in s["tarjeta"]
        assert s.get("zona_horaria") and "Zona Horaria" in s["tarjeta"]   # UTC offset
        assert s.get("sesion_mercado") and "Mercado:" in s["tarjeta"]   # sesión
        assert "FUZION FX" in s["tarjeta"]                     # nombre del bot


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


def test_matriz_varios_tiempos_una_tarjeta_por_tiempo():
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
            tabla={"EURCHF": {"1": [[5, 60.0]], "3": [[5, 70.0]]}},
            repo=HistoryRepository(os.path.join(d, "h.db")),
            is_open_fn=lambda p: True, expiries=[1, 3])     # la matriz: 1m y 3m
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == 2                          # una tarjeta por tiempo
        nombres = {r._cola.get_nowait()["nombre_bot"] for _ in range(2)}
        assert nombres == {"FUZION FX 1M", "FUZION FX 3M"}


def test_payout_bajo_no_encola():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))       # payout_min = 79 por defecto
        r._payouts["EURCHF"] = 70                      # paga poco -> no costo-efectivo
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == 0                     # pago bajo -> callado


def test_payout_alto_encola_con_pago_en_tarjeta():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85                       # paga bien
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() >= 1
        s = r._cola.get_nowait()
        assert s["payout"] == 85
        assert "Pago" in s["tarjeta"]                   # el pago sale en la tarjeta


def test_on_assets_guarda_payout():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        # Formato de PO: lista de activos; parse_assets extrae el payout por rango.
        r._on_assets([["id", "EURCHF", 1, 85], ["id", "GBPCHF", 1, 82]])
        assert r._payouts.get("EURCHF") == 85 or r._payouts.get("EURCHF") is not None


def test_grafico_genera_png():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        velas = [{"timestamp": 1_700_000_000_000 + i * 60_000, "open": 1.08 + i * 1e-4,
                  "high": 1.081 + i * 1e-4, "low": 1.079 + i * 1e-4,
                  "close": 1.0805 + i * 1e-4, "volume": 1.0} for i in range(30)]
        r.repo.record_many("EURCHF", "M1", velas)
        ruta = r._grafico("EURCHF", "PUT", 3)
        assert ruta is not None and os.path.exists(ruta)   # generó el PNG


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
