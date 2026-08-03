"""
bot/test_motor_autonomo.py
==========================
Valida SIN RED el núcleo del motor autónomo: reconoce OPERAR (y solo OPERAR), saca la
dirección y el tiempo sugerido, arma la tarjeta con hora de entrada, escanea una vuelta
quedándose con los pares que operan, y el anti-repetición no deja spamear la misma señal
hasta que pasa el cooldown.
"""
import asyncio
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.motor_autonomo import (es_operar, lado, tarjeta, escanear_vuelta,
                                Antirepeticion, correr, _expiry_sugerido)


def _res(veredicto, direccion="⬆️ UP (CALL)", fuerza=0.82, coinc="3/4", por_tiempo=None):
    return {"veredicto": veredicto, "direccion": direccion, "fuerza": fuerza,
            "coinciden": coinc, "por_tiempo": por_tiempo or {}}


def test_es_operar_distingue_veredictos():
    assert es_operar(_res("✅ OPERAR"))
    assert not es_operar(_res("🚫 NO OPERAR"))
    assert not es_operar(_res("🟡 OPCIONAL"))
    assert not es_operar({"veredicto": "🚫 MERCADO CERRADO"})
    assert not es_operar({})


def test_lado_saca_direccion():
    assert lado(_res("✅ OPERAR", "⬆️ UP (CALL)")) == "CALL"
    assert lado(_res("✅ OPERAR", "⬇️ DOWN (PUT)")) == "PUT"
    assert lado({"direccion": "😴 mercado plano"}) is None


def test_expiry_sugerido_toma_el_corto_confirmado():
    # 2m y 5m confirmados -> sugiere 2m (el más corto que confirma).
    pt = {120: {"confirmado": True}, 300: {"confirmado": True}, 60: {"confirmado": False}}
    assert _expiry_sugerido(_res("✅ OPERAR", por_tiempo=pt)) == 2
    # sin confirmados conocidos -> 3m por defecto.
    assert _expiry_sugerido(_res("✅ OPERAR", por_tiempo={})) == 3


def test_tarjeta_trae_lo_esencial():
    t = tarjeta("GBPUSD", _res("✅ OPERAR", "⬇️ DOWN (PUT)", 0.8, "3/4"), seg=90,
                ahora=datetime(2026, 8, 3, 12, 0, 0))
    assert "GBPUSD" in t and "PUT" in t
    assert "HORA DE ENTRADA: 12:01:30" in t          # 12:00:00 + 90s
    assert "Convergencia: 3/4" in t


def test_escanear_vuelta_solo_los_que_operan():
    async def analizar(par, exp):
        tabla = {"GBPUSD": _res("✅ OPERAR"),
                 "EURUSD": _res("🚫 NO OPERAR"),
                 "USDCHF": {"veredicto": "🚫 MERCADO CERRADO"}}
        return tabla[par], 60, 100
    ops = asyncio.get_event_loop().run_until_complete(
        escanear_vuelta(analizar, ["GBPUSD", "EURUSD", "USDCHF"]))
    assert [p for p, _, _ in ops] == ["GBPUSD"]      # solo el que opera


def test_antirepeticion_respeta_cooldown():
    reloj = {"t": 1000.0}
    anti = Antirepeticion(cooldown_seg=300, reloj=lambda: reloj["t"])
    assert anti.nueva("EURUSD", "CALL")              # primera: pasa
    assert not anti.nueva("EURUSD", "CALL")          # repetida ya: se bloquea
    assert anti.nueva("EURUSD", "PUT")               # otra dirección: pasa
    reloj["t"] += 301                                # pasó el cooldown
    assert anti.nueva("EURUSD", "CALL")              # ahora sí, de nuevo


def test_correr_envia_solo_lo_nuevo():
    # Un par opera siempre; con cooldown alto, en 3 vueltas debe enviarse UNA vez.
    enviados = []
    reloj = {"t": 0.0}

    async def analizar(par, exp):
        return _res("✅ OPERAR", "⬆️ UP (CALL)"), 60, 100

    async def enviar(texto):
        enviados.append(texto)

    async def _corta():
        # Corre `correr` y lo cancela tras dejar pasar unas vueltas (pausa_par=0).
        tarea = asyncio.ensure_future(
            correr(analizar, enviar, ["EURUSD"], pausa_par=0,
                   cooldown_seg=1e9, reloj=lambda: reloj["t"]))
        await asyncio.sleep(0.05)
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass

    asyncio.get_event_loop().run_until_complete(_corta())
    assert len(enviados) == 1                          # no spameó: una sola señal
    assert "EURUSD" in enviados[0] and "CALL" in enviados[0]


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
