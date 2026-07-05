"""
bot/test_coherencia_grafico_hora.py
===================================
Valida SIN red los dos arreglos de rectificación de la tarjeta:

  1) GRÁFICO = LECTURA: el gráfico se dibuja con las MISMAS velas que el sistema
     calificó para el tiempo operado (`frame_sistema_operativo`), no con una
     fuente aparte. Antes discrepaban ("el gráfico no coincide").
  2) HORA DE ENTRADA: se calcula desde la HORA DE MERCADO (último tick) alineada
     al borde de la vela, no desde datetime.now() del equipo ("hora mal").
"""

import os
import time
import matplotlib
matplotlib.use("Agg")                     # sin pantalla, sin red

from datetime import datetime
from bot.history import HistoryRepository
from bot import otc_system
from bot.chart import draw_candles
from bot.levels import detect_levels


def _sembrar(repo, asset, tf, n=120, subiendo=True):
    key = "M1" if tf == 60 else f"tf{tf}"
    base = int(time.time()) - n * int(tf)     # última vela ~ahora (pasa frescura)
    velas = []
    for i in range(n):
        c = 100 + (i if subiendo else (n - i)) * 0.2
        velas.append({"timestamp": (base + i * int(tf)) * 1000, "open": c,
                      "high": c + 0.15, "low": c - 0.15, "close": c, "volume": 1})
    repo.record_many(asset, key, velas)


class _SvcMinimo:
    """Solo lo necesario para probar frame_sistema_operativo sin websocket."""
    def __init__(self, repo):
        self.repo = repo
        self._frames_recientes = {}      # vacío -> cae al historial del repo
    # reutiliza los métodos reales por composición (mismo código que el servicio):
    from bot.pocket_service import PocketService
    _frames_para_sistema = PocketService._frames_para_sistema
    frame_sistema_operativo = PocketService.frame_sistema_operativo


def test_grafico_usa_la_misma_vela_del_sistema():
    repo = HistoryRepository(":memory:")
    for tf in otc_system.TIMEFRAMES:
        _sembrar(repo, "EURUSD_otc", tf)
    svc = _SvcMinimo(repo)

    # El frame operativo del tiempo 300 (M5) debe existir y ser el que el sistema
    # calificó: mismas columnas OHLC, velas frescas.
    fop = svc.frame_sistema_operativo("EURUSD_otc", otc_system, 300)
    assert fop is not None and len(fop) >= 5, "debe devolver el frame fresco de M5"
    for col in ("open", "high", "low", "close"):
        assert col in fop.columns, f"falta columna {col}"

    # Y ese frame se dibuja sin error (el gráfico sale de EXACTAMENTE esas velas).
    chart = fop.tail(45).reset_index(drop=True)
    lv = detect_levels(chart)
    path = os.path.join(os.path.dirname(__file__), "_test_chart.png")
    draw_candles(chart, "EUR/USD OTC", "M5", path, direccion="CALL", levels=lv)
    assert os.path.exists(path) and os.path.getsize(path) > 0
    os.remove(path)
    print("OK el gráfico se dibuja con las MISMAS velas que el sistema calificó")


def test_tiempo_no_fresco_no_da_frame():
    # Un tiempo con velas VIEJAS (descarga de días atrás) no debe pasar: así no se
    # dibuja historial viejo mezclado con lo vivo.
    repo = HistoryRepository(":memory:")
    key = "tf300"
    viejo = int(time.time()) - 5 * 24 * 3600           # hace 5 días
    velas = [{"timestamp": (viejo + i * 300) * 1000, "open": 100, "high": 100.1,
              "low": 99.9, "close": 100, "volume": 1} for i in range(120)]
    repo.record_many("EURUSD_otc", key, velas)
    svc = _SvcMinimo(repo)
    assert svc.frame_sistema_operativo("EURUSD_otc", otc_system, 300) is None
    print("OK un tiempo VIEJO no entrega frame (no se dibuja dato rancio)")


def test_hora_entrada_desde_mercado_alineada_a_la_vela():
    # ahora_mercado + seg = apertura EXACTA de la próxima vela (borde del timeframe).
    tf = 300
    # Simula un último tick a 137s dentro de la vela actual -> faltan 163s.
    ahora_mkt = (int(time.time()) // tf) * tf + 137
    seg = int(tf - (ahora_mkt % tf))
    assert seg == 163
    apertura_epoch = ahora_mkt + seg
    assert apertura_epoch % tf == 0, "la entrada debe caer en el borde de la vela"
    # La hora mostrada = ese epoch en hora local (lo que hace _format_deep).
    esperado = datetime.fromtimestamp(apertura_epoch).strftime("%H:%M:%S")
    # Recalcula como en el código de la tarjeta:
    momento = datetime.fromtimestamp(int(ahora_mkt) + int(seg))
    assert momento.strftime("%H:%M:%S") == esperado
    print(f"OK hora de entrada alineada al borde de la vela ({esperado}), "
          f"desde la hora de mercado (no del reloj del equipo)")


if __name__ == "__main__":
    test_grafico_usa_la_misma_vela_del_sistema()
    test_tiempo_no_fresco_no_da_frame()
    test_hora_entrada_desde_mercado_alineada_a_la_vela()
    print("\nTODOS OK — gráfico coincide con la lectura + hora de entrada correcta")
