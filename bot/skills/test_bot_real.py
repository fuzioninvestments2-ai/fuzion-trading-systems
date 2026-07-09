"""
bot/skills/test_bot_real.py
===========================
Valida (sin red) el ML online, el skill de régimen y el bot completo en modo replay.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.skills.base_skill import CALL, PUT, NEUTRAL
from bot.skills.skill_online_ml import SkillOnlineML
from bot.skills.skill_regime import SkillMarketRegime, calcular_adx
from bot.skills.bot_real import PocketOptionRealBot, crear_manager


def _df(closes):
    filas = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        filas.append({"timestamp": 1_000_000_000_000 + i * 60000, "open": o,
                      "high": max(o, c) + 0.01, "low": min(o, c) - 0.01,
                      "close": c, "volume": 10.0})
        prev = c
    return pd.DataFrame(filas)


def _md(closes):
    return {"df": _df(closes), "pair": "EURUSD", "timeframe": 60}


def test_ml_entrena_y_vota():
    ml = SkillOnlineML(learning_rate=0.05)
    # Antes de entrenar: NEUTRAL.
    v0 = ml.analyze(_md([100 + np.sin(i / 5) for i in range(60)]))
    assert v0["direction"] == NEUTRAL
    # Entrenar con muchos ejemplos donde 'sube' es la verdad → aprende a votar CALL.
    for _ in range(60):
        ml.analyze(_md([100 + i * 0.1 for i in range(60)]))
        ml.learn({"real_direction": CALL})
    assert ml.predictions >= 30
    v = ml.analyze(_md([100 + i * 0.1 for i in range(60)]))
    assert v["direction"] in (CALL, PUT)          # ya no está NEUTRAL entrenando


def test_adx_alto_en_tendencia():
    tend = _df([100 + i * 0.2 for i in range(80)])
    rango = _df([100 + np.sin(i / 3) * 0.5 for i in range(80)])
    assert calcular_adx(tend) > calcular_adx(rango)


def test_regime_elige_estrategia():
    v = SkillMarketRegime().analyze(_md([100 + np.sin(i / 4) * 0.1 for i in range(80)]))
    assert "reversión" in v["reason"] or "momentum" in v["reason"]


def test_manager_tiene_4_skills():
    m = crear_manager(weights_path=os.devnull)
    assert len(m.skills) == 4
    for sid in ("SkillReversion", "SkillMomentum", "SkillMarketRegime", "SkillOnlineML"):
        assert sid in m.skills


def test_bot_replay_corre_y_aprende():
    bot = PocketOptionRealBot(pair="EURUSD", weights_path=os.devnull,
                              estado_path=os.devnull)
    ruido = [100 + np.sin(i / 5) * 0.3 for i in range(400)]
    r = bot.run_replay(_df(ruido))
    assert r["señales_emitidas"] >= 0
    assert "win_rate" in r and "pesos" in r


def test_procesar_emite_estructura():
    bot = PocketOptionRealBot(weights_path=os.devnull, estado_path=os.devnull)
    s = bot.procesar(_df([100 + np.sin(i / 4) * 0.2 for i in range(80)]))
    for k in ("pair", "direccion", "confianza", "emitir", "precio"):
        assert k in s


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
            except Exception as e:
                fallos += 1
                print(f"ERR  {nombre}: {e}")
    sys.exit(1 if fallos else 0)
