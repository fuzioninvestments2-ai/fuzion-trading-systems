"""
bot/skills/backtest_ensemble.py
===============================
Backtest HONESTO del ensemble de skills sobre datos históricos REALES. NO simula
el resultado: usa el movimiento real del precio. El ensemble APRENDE en línea
(ajusta pesos vela a vela) tal como haría en vivo, y se mide su acierto separando
in-sample (1ª mitad temporal) de out-of-sample (2ª mitad). Un borde solo vale si
sobrevive en la 2ª mitad.

Salida por timeframe: nº de señales, win-rate IS, win-rate OOS, pesos aprendidos.
Referencia: 50% = azar. En binarias con payout 92% el break-even es 52.08%.
"""
import glob
import os

import pandas as pd

from bot.skills.base_skill import NEUTRAL
from bot.skills.skill_manager import SkillManager
from bot.skills.skill_reversion import SkillReversion
from bot.skills.skill_momentum import SkillMomentum

WARMUP = 60                 # velas mínimas antes de operar (bandas + autocorr)
CONF_MIN = 0.55             # confianza mínima del consenso para emitir señal


def _nuevo_manager():
    """Manager fresco (pesos en 1.0) con los skills registrados. Sin persistir."""
    m = SkillManager(weights_path=os.devnull)
    m.register_skill(SkillReversion())
    m.register_skill(SkillMomentum())
    return m


def backtest_df(df, expiry=1, conf_min=CONF_MIN):
    """
    Camina el DataFrame vela a vela. En cada punto: consenso con historia hasta t,
    y si supera conf_min, compara con el movimiento real a `expiry` velas.
    Aprende en línea. Devuelve métricas IS/OOS.
    """
    df = df.sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    mitad = n // 2
    manager = _nuevo_manager()
    res = {"is": [0, 0], "oos": [0, 0], "senales": 0}    # [wins, total] por mitad

    close = df["close"].to_numpy()
    for i in range(WARMUP, n - expiry):
        sub = df.iloc[:i + 1]
        md = {"df": sub, "pair": "?", "timeframe": None}
        cons = manager.get_consensus(md)
        if cons["direction"] == NEUTRAL or cons["confidence"] < conf_min:
            continue
        # Movimiento REAL a `expiry` velas (sin mirar más allá).
        subio = close[i + expiry] > close[i]
        if close[i + expiry] == close[i]:
            continue                                       # empate: no cuenta
        real = "CALL" if subio else "PUT"
        acerto = cons["direction"] == real
        res["senales"] += 1
        mitad_k = "is" if i < mitad else "oos"
        res[mitad_k][0] += int(acerto); res[mitad_k][1] += 1
        # Aprender del resultado REAL (online), como en vivo.
        manager.registrar_win(acerto)
        manager.update_weights(real, cons["details"])

    def wr(par):
        return (par[0] / par[1] * 100) if par[1] else None
    return {"senales": res["senales"], "wr_is": wr(res["is"]), "wr_oos": wr(res["oos"]),
            "n_is": res["is"][1], "n_oos": res["oos"][1], "pesos": manager.stats()["weights"]}


TF_SEG = {"M1": 60, "tf120": 120, "tf180": 180, "tf300": 300, "tf900": 900,
          "tf1800": 1800, "tf3600": 3600, "tf14400": 14400}


def _etq(seg):
    if seg < 3600:
        return f"{seg // 60}m"
    return f"{seg // 3600}h"


def correr_activo(activo, patron="datasets", conf_min=CONF_MIN):
    rutas = sorted(glob.glob(f"{patron}/{activo}__*.csv.gz"))
    print(f"\n{'='*70}\nENSEMBLE · {activo}   (conf_min={conf_min})\n{'='*70}")
    print(f"{'TF':>4} | {'señales':>7} | {'winIS':>6} | {'winOOS':>6} | pesos aprendidos")
    for r in rutas:
        clave = os.path.basename(r).split("__")[1].replace(".csv.gz", "")
        seg = TF_SEG.get(clave)
        if seg is None or seg > 3600:
            continue
        df = pd.read_csv(r)
        if len(df) < 200:
            continue
        m = backtest_df(df)
        wis = f"{m['wr_is']:.1f}%" if m["wr_is"] is not None else "—"
        woos = f"{m['wr_oos']:.1f}%" if m["wr_oos"] is not None else "—"
        print(f"{_etq(seg):>4} | {m['senales']:>7} | {wis:>6} | {woos:>6} | {m['pesos']}")


if __name__ == "__main__":
    from bot.estudio_fx import activos_reales
    print("Backtest del ensemble sobre datos reales. 50% = azar; 52.08% = break-even 92%.")
    for a in activos_reales():
        correr_activo(a)
