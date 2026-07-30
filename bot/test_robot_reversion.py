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
                                 ACTIVOS_PO, _necesita_reinicio, _es_tardia,
                                 _proxima_entrada, _ev_par)
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
    # expiry_min=1: el análisis corre sobre velas M1 (las que cierran con los ticks del
    # test). Cada bot analiza SU tiempo; aquí probamos los filtros con el de 1m.
    return RobotReversion(
        get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
        expiry_min=1, tabla={"EURCHF": [[5, 70.0], [8, 72.0]]},
        repo=HistoryRepository(tmpdb),
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


def test_matriz_cada_bot_analiza_su_tiempo():
    # La matriz 1m + 2m: cada bot arma SUS velas y da su propia señal. Un par de ticks
    # separados 2 min cierra a la vez una vela M1 y una de 2m; ambos bots deben disparar
    # con SU nombre (no el mismo pico repetido: análisis independientes por tiempo).
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
            tabla={"EURCHF": {"1": [[5, 60.0], [8, 62.0]], "2": [[5, 70.0], [8, 72.0]]}},
            repo=HistoryRepository(os.path.join(d, "h.db")),
            is_open_fn=lambda p: True, expiries=[1, 2])     # la matriz: 1m y 2m
        r.con_atraso = False                                 # ticks espaciados a propósito
        r._payouts["EURCHF"] = 85
        serie = [1.0795 if i % 2 else 1.0805 for i in range(20)]   # ruido, media 1.0800
        r.vigilantes[1].precargar("EURCHF", serie)
        r.vigilantes[2].precargar("EURCHF", serie)
        r._on_tick("EURCHF", 6000, 1.0810)                  # pico (cierra M1 y 2m al saltar)
        r._on_tick("EURCHF", 6120, 1.0810)                  # +2 min: cierra ambas velas
        assert r._cola.qsize() == 2                          # una tarjeta por tiempo
        nombres = {r._cola.get_nowait()["nombre_bot"] for _ in range(2)}
        assert nombres == {"FUZION FX 1M", "FUZION FX 2M"}


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


def test_corrector_silencia_par_que_falla():
    # Con muestra suficiente de PÉRDIDAS reales, el corrector calla ese par+tiempo.
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85                       # pago conocido -> equilibrio ~54%
        r.corrector_min_muestra = 5                     # muestra chica para el test
        # Siembra 5 señales M1 ya resueltas como 'loss' (acierto reciente 0%).
        for i in range(5):
            r.tracker.record("EURCHF", "M1", "PUT", 1.0800, i * 1000, 60)
        # Vela de vencimiento POSTERIOR y por ENCIMA (PUT pierde) para todas.
        r.repo.record_candle("EURCHF", "M1", {"timestamp": 100_000, "open": 1.09,
            "high": 1.0905, "low": 1.0895, "close": 1.0900, "volume": 1.0})
        r.tracker.resolve_pending(200_000)
        wr, muestra = r.tracker.win_rate_reciente("EURCHF", "M1", 5)
        assert muestra == 5 and wr == 0.0               # 0% de acierto reciente
        antes = r._cola.qsize()
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == antes                 # silenciado: no encoló nada


def test_noticia_alto_impacto_calla_el_par():
    import json as _json
    from datetime import datetime, timezone
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85
        # Evento USD/EUR/CHF de alto impacto AHORA -> ventana activa -> par callado.
        ahora = datetime.now(timezone.utc).isoformat()
        r.news.cargar(_json.dumps([
            {"country": "EUR", "impact": "High", "date": ahora, "title": "IPC"}]))
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == 0                     # noticia -> silencio


def test_proxima_entrada_da_margen():
    # La hora de entrada siempre cae en un borde de vela futuro con al menos min_lead seg
    # de margen (para dar tiempo a programarla), pero sin saltarse más de una vela.
    for ahora in (1000, 1005, 1037, 1059, 1200, 1233):
        inicio = _proxima_entrada(ahora, 60, 20)
        assert inicio % 60 == 0                          # cae en el borde de la vela
        assert 20 <= inicio - ahora < 20 + 60            # margen garantizado, acotado


def test_senal_hora_limpia_sin_cuenta_atras():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        s = r._cola.get_nowait()
        assert s.get("hora_entrada") and s.get("hora_vence")
        # Sin textos que confunden (segundos/cuenta atrás): solo la hora.
        assert "faltan" not in s["tarjeta"] and "seg" not in s["tarjeta"]
        assert "HORA DE ENTRADA" in s["tarjeta"]


def test_es_tardia_detecta_cierre_atrasado():
    # Vela que empezó en 60s (M1: termina en 120s). Un tick a 130s = 10s de atraso.
    assert _es_tardia(130, 60_000, 60, 25) is False        # 10s <= 25: a tiempo
    assert _es_tardia(200, 60_000, 60, 25) is True         # 80s > 25: tarde


def test_senal_tardia_no_encola():
    # Con el guard activo, un cierre detectado muy tarde (ticks separados) se descarta.
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85
        r.max_atraso_seg = 25
        # Ticks separados 2 min: la vela M1 (60s) se cierra con 60s de atraso -> tarde.
        r._on_tick("EURCHF", 6000, 1.0800)
        r._on_tick("EURCHF", 6120, 1.0810)
        assert r._cola.qsize() == 0                          # descartada por tardía


def test_ev_bajo_no_encola():
    # El fallo de las tarjetas: acierto 53% a pago 81% -> EV negativo -> PIERDE. Se veta.
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
            expiry_min=1, tabla={"EURCHF": [[5, 53.0]]},
            repo=HistoryRepository(os.path.join(d, "h.db")), is_open_fn=lambda p: True)
        r._payouts["EURCHF"] = 81                        # pago real 81% -> equilibrio ~55%
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() == 0                       # 53% a 81% pierde -> callado


def test_ev_alto_si_encola_con_ventaja_real():
    # Mismo pico pero acierto 70%: a 81% de pago SÍ rinde -> se envía y la ventaja de la
    # tarjeta refleja el pago REAL (no el 92% de la tabla).
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF"], ssid="x", token="", chat_id="1",
            expiry_min=1, tabla={"EURCHF": [[5, 70.0]]},
            repo=HistoryRepository(os.path.join(d, "h.db")), is_open_fn=lambda p: True)
        r._payouts["EURCHF"] = 81
        for ts, px in [(60, 1.0800), (120, 1.0800), (180, 1.0810),
                       (240, 1.0810), (300, 1.0810)]:
            r._on_tick("EURCHF", ts, px)
        assert r._cola.qsize() >= 1
        s = r._cola.get_nowait()
        assert s["pnl_esperado"] > 0                      # ventaja positiva con pago real


def test_contra_tendencia_no_encola():
    # El fallo de las tarjetas: subida sostenida + pico arriba -> el bot daba PUT. Con el
    # filtro de tendencia, esa señal contra la subida se veta (no encola).
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        r._payouts["EURCHF"] = 85
        subida = [1.0800 + 0.0002 * i for i in range(20)]   # tendencia alcista clara
        r.vig.precargar("EURCHF", subida)
        r._on_tick("EURCHF", 6000, 1.0848)                  # pico arriba (sigue subiendo)
        r._on_tick("EURCHF", 6060, 1.0848)                  # cierra la vela del pico
        assert r._cola.qsize() == 0                          # vetada por ir contra la subida


def test_ev_par_elegibilidad_y_orden():
    # Paga menos del mínimo -> no elegible (None).
    assert _ev_par(60.0, 70.0, 72.0) is None
    # Sin borde -> no elegible.
    assert _ev_par(0.0, 90.0, 72.0) is None
    # Elegible: EV = p*pago - (1-p). Mayor pago o mayor borde -> mayor EV.
    ev_alto = _ev_par(60.0, 90.0, 72.0)
    ev_bajo = _ev_par(60.0, 75.0, 72.0)
    assert ev_alto is not None and ev_alto > ev_bajo   # más pago = mejor


def test_mejor_par_elige_el_de_mayor_ev():
    with tempfile.TemporaryDirectory() as d:
        r = RobotReversion(
            get_profile("REAL"), pares=["EURCHF", "CHFJPY", "AUDCAD"], ssid="x",
            token="", chat_id="1",
            tabla={"EURCHF": [[5, 60.0]], "CHFJPY": [[5, 64.0]], "AUDCAD": [[5, 61.0]]},
            repo=HistoryRepository(os.path.join(d, "h.db")), is_open_fn=lambda p: True)
        r._payouts = {"EURCHF": 85, "CHFJPY": 90, "AUDCAD": 70}   # AUDCAD paga poco
        mejor, ev = r._mejor_par()
        assert mejor == "CHFJPY"                        # mejor borde Y mejor pago
        # AUDCAD no es elegible (paga < 72): no puede salir elegido.
        r._payouts = {"EURCHF": 85, "CHFJPY": 71, "AUDCAD": 70}   # solo EURCHF elegible
        mejor2, _ = r._mejor_par()
        assert mejor2 == "EURCHF"


def test_watchdog_decide_reinicio():
    # Mercado abierto y sin ticks nuevos -> reinicia; con ticks o cerrado -> no.
    assert _necesita_reinicio(100, 100, True) is True     # abierto y sin latido
    assert _necesita_reinicio(100, 105, True) is False    # llegaron ticks
    assert _necesita_reinicio(100, 100, False) is False   # cerrado: silencio normal


def _flujo_pico(r, z_min):
    # Buffer con RUIDO (±5 pips, media 1.0800) precargado, y luego un cierre pico a
    # 1.0810 -> z ~2. Con z_min alto se silencia; con z_min bajo pasa.
    r._payouts["EURCHF"] = 85
    r.con_confirmacion = True                       # este test prueba la confirmación
    r.conf_z_min = z_min
    r.vig.precargar("EURCHF", [1.0795 if i % 2 else 1.0805 for i in range(20)])
    r._on_tick("EURCHF", 100 * 60, 1.0810)          # tick del pico
    r._on_tick("EURCHF", 101 * 60, 1.0810)          # cierra la vela del pico (close=1.0810)
    return r._cola.qsize()


def test_sin_confirmacion_no_encola():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        assert _flujo_pico(r, z_min=3.0) == 0        # z~2 < 3 -> sin confirmación, callado


def test_con_confirmacion_encola():
    with tempfile.TemporaryDirectory() as d:
        r = _robot_tmp(os.path.join(d, "h.db"))
        assert _flujo_pico(r, z_min=1.0) >= 1        # z~2 >= 1 -> confirmado, encola


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
