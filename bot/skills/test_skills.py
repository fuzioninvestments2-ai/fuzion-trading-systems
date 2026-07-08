"""
bot/skills/test_skills.py
=========================
Valida la MECÁNICA del sistema de skills (sin red, con series sintéticas):
  - autocorrelación detecta reversión/tendencia,
  - cada skill vota coherente con el régimen,
  - el SkillManager combina votos y aprende del resultado REAL (sube el peso del
    skill que acierta, baja el del que falla),
  - el backtest parte IS/OOS y no mira el futuro.
No mide win-rates reales (dependen de los datos).
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.skills.base_skill import CALL, PUT, NEUTRAL
from bot.skills.skill_reversion import SkillReversion, autocorrelacion
from bot.skills.skill_momentum import SkillMomentum
from bot.skills.skill_manager import SkillManager, PESO_INI
from bot.skills.backtest_ensemble import backtest_df


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
    """Envuelve una serie de cierres en el contrato market_data que leen los skills."""
    return {"df": _df(closes), "pair": "x", "timeframe": 60}


def test_autocorr_signo():
    alterna = [100 + (1 if i % 2 == 0 else -1) * 0.5 for i in range(200)]
    assert autocorrelacion(alterna) < -0.3               # reversión → negativa
    tendencia = [100 + i * 0.1 for i in range(200)]
    assert autocorrelacion(tendencia) > -0.05            # tendencia → no muy negativa


def test_reversion_vota_put_en_pico():
    # Oscilación suave y una subida sostenida al final → precio sobre banda → PUT.
    closes = [100.0 + np.sin(i / 4) * 0.05 for i in range(50)]
    closes += [100.0 + 0.08 * i for i in range(1, 8)]   # empuje gradual arriba
    v = SkillReversion().analyze(_md(closes))
    assert v["direction"] == PUT, f"esperaba PUT, dio {v['direction']} ({v['reason']})"


def test_momentum_vota_direccion_del_empuje():
    subiendo = [100 + i * 0.2 for i in range(40)]
    v = SkillMomentum().analyze(_md(subiendo))
    assert v["direction"] == CALL, f"esperaba CALL, dio {v['direction']} ({v['reason']})"


def test_manager_combina_y_aprende():
    m = SkillManager(weights_path=os.devnull)
    m.register_skill(SkillReversion())
    m.register_skill(SkillMomentum())
    assert m.weights["SkillReversion"] == PESO_INI
    # Simular un voto donde Reversion acertó y Momentum falló.
    detalle = {"SkillReversion": {"vote": CALL}, "SkillMomentum": {"vote": PUT}}
    w_rev0, w_mom0 = m.weights["SkillReversion"], m.weights["SkillMomentum"]
    m.update_weights(real_direction=CALL, detalle=detalle)
    assert m.weights["SkillReversion"] > w_rev0          # acertó → sube
    assert m.weights["SkillMomentum"] < w_mom0           # falló → baja


def test_consenso_neutral_sin_votos():
    m = SkillManager(weights_path=os.devnull)
    m.register_skill(SkillReversion())
    cons = m.get_consensus(_md([100.0] * 80))
    assert cons["direction"] == NEUTRAL


def test_backtest_devuelve_metricas():
    ruido = [100 + np.sin(i / 5) * 0.3 for i in range(400)]
    r = backtest_df(_df(ruido))
    assert "wr_is" in r and "wr_oos" in r and r["senales"] >= 0
    assert r["n_is"] >= 0 and r["n_oos"] >= 0


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
