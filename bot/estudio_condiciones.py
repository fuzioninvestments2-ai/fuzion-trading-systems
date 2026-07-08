"""
bot/estudio_condiciones.py
==========================
¿La REVERSIÓN funciona solo en ciertas CONDICIONES? Mide el win-rate de la señal de
reversión (precio fuera de las Bandas de Bollinger → apostar al retorno) segmentado
por HORA UTC (sesión) y por RÉGIMEN DE VOLATILIDAD, con validación out-of-sample
temporal (1ª mitad del tiempo = IS, 2ª mitad = OOS). Un borde condicional solo cuenta
si supera 52.08% (break-even payout 92%) en AMBAS mitades y con muestra suficiente.

Señal de reversión (vectorizada, rápida):
  media/desv de 20 velas → bandas ±2σ. Si el cierre pincha la banda superior → PUT;
  la inferior → CALL. Resultado = dirección de la vela siguiente.

Honestidad: se prueban muchas celdas (24 horas × 4 regímenes). Por el riesgo de
"encontrar algo por azar", se EXIGE persistencia OOS y n alto; se avisa lo que no
llega. No se ajusta a la 1ª mitad y se canta victoria: debe repetir en la 2ª.
"""
import glob
import os

import numpy as np
import pandas as pd

BREAKEVEN = 52.08
N_MIN = 200                # mínimo de señales por celda y mitad para no medir ruido
BORDE = 52.08              # win-rate exigido en IS y OOS

# Acumuladores globales (todas los pares juntos): clave → {"is":[w,n], "oos":[w,n]}
por_hora = {}
por_vol = {}


def _reg(dic, clave, mitad, gano):
    d = dic.setdefault(clave, {"is": [0, 0], "oos": [0, 0]})
    d[mitad][0] += int(gano); d[mitad][1] += 1


def señal_reversion(df):
    """
    Señal de reversión POR VELA (maximiza muestra para el análisis condicional):
    apostar CONTRA el último movimiento. Si la vela cerró al alza → PUT (esperar
    retorno); si a la baja → CALL. Resultado = dirección de la vela siguiente. Con
    autocorrelación negativa, esto gana algo >50%; buscamos en qué condición >52%.
    Devuelve DataFrame filtrado (sin empates) con dir, gano, hora, vol_rel.
    """
    close = df["close"].astype(float)
    subio_actual = close.diff() > 0                          # ¿esta vela cerró al alza?
    direc = np.where(subio_actual, -1, 1)                    # al alza→PUT ; a la baja→CALL
    fut = close.shift(-1)
    subio_fut = (fut > close).to_numpy()
    empate = (fut == close).to_numpy() | fut.isna().to_numpy() | close.diff().isna().to_numpy()
    gano = ((direc == 1) & subio_fut) | ((direc == -1) & ~subio_fut)
    desv = close.rolling(20).std()
    media = close.rolling(20).mean()
    hora = ((df["timestamp"].to_numpy() // 3_600_000) % 24).astype(int)
    vol_rel = (desv / media).to_numpy()
    out = pd.DataFrame({"dir": direc, "gano": gano, "hora": hora, "vol": vol_rel,
                        "empate": empate})
    return out[(~out["empate"]) & (~out["vol"].isna())].reset_index(drop=True)


def _rutas_reales(patron="datasets"):
    todas = glob.glob(f"{patron}/**/*__*.csv.gz", recursive=True)
    return sorted(r for r in todas
                  if "_otc" not in os.path.basename(r).lower()
                  and "/otc/" not in r.replace(os.sep, "/").lower())


def procesar(patron="datasets", claves=("M1", "tf120")):
    """Acumula señales de reversión de todos los pares en 1m y 2m, con split temporal."""
    rutas = [r for r in _rutas_reales(patron)
             if os.path.basename(r).split("__")[1].replace(".csv.gz", "") in claves]
    for r in rutas:
        df = pd.read_csv(r).sort_values("timestamp").reset_index(drop=True)
        if len(df) < 400:
            continue
        s = señal_reversion(df)
        if len(s) < 50:
            continue
        # Split temporal: primera mitad de las SEÑALES en el tiempo = IS.
        medio = len(s) // 2
        # Cuartiles de volatilidad de ESTE par (regímenes propios).
        q = pd.qcut(s["vol"].rank(method="first"), 4, labels=["muy_baja", "baja", "alta", "muy_alta"])
        for idx, row in enumerate(s.itertuples(index=False)):
            mitad = "is" if idx < medio else "oos"
            _reg(por_hora, int(row.hora), mitad, row.gano)
            _reg(por_vol, str(q.iloc[idx]), mitad, row.gano)


def _wr(par):
    return (par[0] / par[1] * 100) if par[1] else None


def reporte():
    print(f"\nBreak-even payout 92%: {BREAKEVEN:.2f}%  ·  borde exigido >{BORDE}% en IS Y OOS (n>={N_MIN})\n")
    print("POR HORA UTC (reversión):")
    print(f"{'hora':>4} | {'IS':>16} | {'OOS':>16}")
    bordes = []
    for h in range(24):
        if h not in por_hora:
            continue
        d = por_hora[h]
        wi, wo = _wr(d["is"]), _wr(d["oos"])
        si = f"{wi:5.1f}% (n={d['is'][1]:5})" if wi is not None else "s/n"
        so = f"{wo:5.1f}% (n={d['oos'][1]:5})" if wo is not None else "s/n"
        marca = ""
        if (wi and wo and d["is"][1] >= N_MIN and d["oos"][1] >= N_MIN
                and wi > BORDE and wo > BORDE):
            marca = "  ← BORDE"
            bordes.append(("hora", h, wi, wo))
        print(f"{h:>4} | {si:>16} | {so:>16}{marca}")

    print("\nPOR RÉGIMEN DE VOLATILIDAD (reversión):")
    for k in ("muy_baja", "baja", "alta", "muy_alta"):
        if k not in por_vol:
            continue
        d = por_vol[k]
        wi, wo = _wr(d["is"]), _wr(d["oos"])
        si = f"{wi:5.1f}% (n={d['is'][1]:6})" if wi is not None else "s/n"
        so = f"{wo:5.1f}% (n={d['oos'][1]:6})" if wo is not None else "s/n"
        marca = ""
        if (wi and wo and d["is"][1] >= N_MIN and d["oos"][1] >= N_MIN
                and wi > BORDE and wo > BORDE):
            marca = "  ← BORDE"
            bordes.append(("vol", k, wi, wo))
        print(f"  {k:>9} | IS {si} | OOS {so}{marca}")

    print("\n" + "=" * 60)
    if bordes:
        print("CONDICIONES CON BORDE (>52% en IS y OOS):")
        for tipo, k, wi, wo in bordes:
            print(f"  {tipo} {k}: IS {wi:.1f}% · OOS {wo:.1f}%  ← investigar")
    else:
        print("NINGUNA condición supera 52% en ambas mitades. La reversión no tiene")
        print("un régimen/hora donde sea rentable de forma persistente (con estos datos).")
    print("=" * 60)


if __name__ == "__main__":
    print("Estudio de CONDICIONES de la reversión (hora + volatilidad), out-of-sample.")
    procesar()
    reporte()
