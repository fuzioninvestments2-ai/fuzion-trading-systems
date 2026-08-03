"""
bot/validar_edge.py
===================
VALIDA UN EDGE CANDIDATO con dureza antes de arriesgar dinero. `buscar_edge` encontró que
5m en la sesión de Cierre gana (55%); pero como se probaron ~32 celdas, por azar se espera
1-2 falsos positivos. Esta herramienta aísla ESA hipótesis y le pregunta lo único que
importa: ¿es ventaja real y estable, o suerte de un período/par?

Tres pruebas:
  1. BONFERRONI: reajusta la confianza por haber mirado muchas celdas. El límite inferior
     con z corregido debe SEGUIR por encima del equilibrio; si no, era ruido de elegir el
     máximo de muchos.
  2. AÑO POR AÑO (walk-forward): el acierto debe ganar en la MAYORÍA de los años, no
     sostenerse por un solo período afortunado.
  3. PAR POR PAR: la ventaja debe ser AMPLIA (varios pares), no un único par que arrastra
     el promedio. Se recalcula quitando el mejor par: si se cae, era concentración.

Solo declara ROBUSTO si pasa las tres. No borra nada; solo lee. Sin red.
Test: bot/test_validar_edge.py.

Uso:
    PYTHONPATH=. python bot/validar_edge.py                       # 5m · Cierre (por defecto)
    PYTHONPATH=. python bot/validar_edge.py --exp 5 --sesion Cierre --pago 92 --tests 32
"""
import math
from statistics import NormalDist

from bot.simulacion import simular_ops
from bot.buscar_edge import SESIONES, _wilson_low


def _z_bonferroni(tests, familia=0.05):
    """z para un intervalo cuya confianza se corrige por haber mirado `tests` celdas
    (Bonferroni, dos colas). Con la misma convención que _wilson_low (z=1.96 ↔ 0.05)."""
    tests = max(1, int(tests))
    alfa = familia / tests
    return NormalDist().inv_cdf(1.0 - alfa / 2.0)


def _cel(ops, equilibrio, z):
    """{n, wins, wr, low} de una lista de ops con el z indicado."""
    n = len(ops)
    wins = sum(1 for o in ops if o["gana"])
    return {"n": n, "wins": wins,
            "wr": (round(wins / n * 100, 1) if n else None),
            "low": _wilson_low(wins, n, z)}


def _anio(ts_ms):
    """Año UTC de una marca de tiempo en ms, sin depender de zona horaria local."""
    # 1970 + días/365.25; entero. Evita datetime para no arrastrar tz.
    import datetime
    return datetime.datetime.utcfromtimestamp(ts_ms / 1000.0).year


def validar(ops_por_par, sesion, payout=85.0, tests=32, min_anio=50):
    """Aísla las ops del `exp`/`sesion` (ya vienen filtradas por exp en ops_por_par) y las
    estresa. Devuelve un dict con las tres pruebas y el veredicto."""
    equilibrio = 100.0 / (1.0 + payout / 100.0)
    test_sesion = dict(SESIONES)[sesion]

    # Todas las ops del edge (todos los pares) que caen en la sesión.
    del_edge = {par: [o for o in ops if test_sesion(o["hora"])]
                for par, ops in ops_por_par.items()}
    todas = [o for ops in del_edge.values() for o in ops]

    z95 = 1.96
    zb = _z_bonferroni(tests)
    global95 = _cel(todas, equilibrio, z95)
    globalbf = _cel(todas, equilibrio, zb)

    # AÑO POR AÑO: reparte por año de entrada (solo años con muestra suficiente).
    por_anio_map = {}
    for o in todas:
        por_anio_map.setdefault(_anio(o["ts"]), []).append(o)
    por_anio = []
    for a in sorted(por_anio_map):
        c = _cel(por_anio_map[a], equilibrio, z95)
        c["anio"] = a
        c["gana"] = bool(c["n"] >= min_anio and c["wr"] is not None and c["wr"] > equilibrio)
        por_anio.append(c)
    anios_validos = [c for c in por_anio if c["n"] >= min_anio]
    frac_anios_gana = (sum(1 for c in anios_validos if c["gana"]) / len(anios_validos)
                       if anios_validos else 0.0)

    # PAR POR PAR + quitar el mejor par (test de concentración).
    por_par = []
    for par, ops in del_edge.items():
        c = _cel(ops, equilibrio, z95)
        c["par"] = par
        por_par.append(c)
    por_par.sort(key=lambda c: (c["wr"] is None, -(c["wr"] or 0.0)))
    mejor_par = por_par[0]["par"] if por_par else None
    sin_mejor = [o for par, ops in del_edge.items() if par != mejor_par for o in ops]
    global_sin_mejor = _cel(sin_mejor, equilibrio, z95)

    # VEREDICTO: robusto solo si pasa las TRES.
    pasa_bonf = globalbf["low"] is not None and globalbf["low"] > equilibrio
    pasa_anios = frac_anios_gana >= 0.6
    pasa_amplitud = (global_sin_mejor["low"] is not None
                     and global_sin_mejor["low"] > equilibrio)
    robusto = bool(pasa_bonf and pasa_anios and pasa_amplitud)

    return {"equilibrio": round(equilibrio, 1), "sesion": sesion,
            "global95": global95, "globalbf": globalbf, "z_bonferroni": round(zb, 2),
            "por_anio": por_anio, "frac_anios_gana": round(frac_anios_gana, 2),
            "por_par": por_par, "mejor_par": mejor_par,
            "global_sin_mejor": global_sin_mejor,
            "pasa_bonferroni": pasa_bonf, "pasa_anios": pasa_anios,
            "pasa_amplitud": pasa_amplitud, "robusto": robusto}


def _ops_exp(df, par, exp, payout, frac_test=0.4):
    """Ops OOS de UN par para UN tiempo: tabla con el 60% de entrenamiento, se corre el
    pipeline sobre el 40% de prueba. Solo ese tiempo (rápido)."""
    import numpy as np
    from bot.tabla_reversion import tabla_par
    df = df.sort_values("timestamp")
    ts = df["timestamp"].astype("int64").tolist()
    cl = df["close"].astype(float).tolist()
    train = np.asarray(cl[:int(len(cl) * 0.6)], dtype=float)
    corte_test = int(len(cl) * (1 - frac_test))
    tr = tabla_par(train, par, exp)
    tabla = {par: {str(exp): [[u, wr] for u, wr, _ in tr]}} if tr else {par: {}}
    return simular_ops(ts[corte_test:], cl[corte_test:], par, exp, tabla, payout=payout)


if __name__ == "__main__":
    import argparse
    import glob
    import os
    import pandas as pd

    ap = argparse.ArgumentParser(description="Valida un edge candidato (por defecto 5m·Cierre).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = todos los reales)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--exp", type=int, default=5)
    ap.add_argument("--sesion", default="Cierre",
                    choices=[n for n, _ in SESIONES])
    ap.add_argument("--pago", type=float, default=85.0)
    ap.add_argument("--tests", type=int, default=32,
                    help="nº de celdas miradas en buscar_edge (para Bonferroni)")
    a = ap.parse_args()

    rutas = [r for r in sorted(glob.glob(f"{a.destino}/*__M1.csv.gz"))
             if "_otc" not in os.path.basename(r).lower()]
    if not rutas:
        rutas = [r for r in sorted(glob.glob("datasets/*__M1.csv.gz"))
                 if "_otc" not in os.path.basename(r).lower()]
    if a.pares:
        rutas = [r for r in rutas if os.path.basename(r).split("__")[0] in a.pares]

    equi = 100.0 / (1.0 + a.pago / 100.0)
    print(f"VALIDACIÓN DE EDGE  ·  {a.exp}m · {a.sesion}  ·  pago {a.pago:.0f}%  ·  "
          f"equilibrio {equi:.1f}%  ·  {len(rutas)} pares  ·  Bonferroni {a.tests} celdas")
    print("=" * 82)

    ops_por_par = {}
    total = len(rutas)
    for idx, r in enumerate(rutas, 1):
        par = os.path.basename(r).split("__")[0]
        print(f"  [{idx}/{total}] {par:8} ...", end="", flush=True)
        try:
            df = pd.read_csv(r)
        except Exception as e:
            print(f" ERROR {e}", flush=True)
            continue
        ops_por_par[par] = _ops_exp(df, par, a.exp, a.pago)
        print(f" {len(df)} velas -> {len(ops_por_par[par])} ops {a.exp}m", flush=True)

    v = validar(ops_por_par, a.sesion, a.pago, a.tests)

    g95, gbf = v["global95"], v["globalbf"]
    print("\n" + "-" * 82)
    print(f"GLOBAL del edge ({a.exp}m·{a.sesion}):  acierto {g95['wr']}%  (n={g95['n']})")
    print(f"  límite95 (normal)      {g95['low']:.1f}%   > equilibrio {v['equilibrio']}%  "
          f"-> {'sí' if g95['low'] > v['equilibrio'] else 'NO'}")
    print(f"  límite Bonferroni z={v['z_bonferroni']}  {gbf['low']:.1f}%   > equilibrio "
          f"{v['equilibrio']}%  -> {'sí' if v['pasa_bonferroni'] else 'NO (era ruido)'}")

    print("\nAÑO POR AÑO (walk-forward):")
    for c in v["por_anio"]:
        marca = "" if c["n"] < 50 else ("  gana" if c["gana"] else "  pierde")
        wr = f"{c['wr']:.0f}%" if c["wr"] is not None else "-"
        print(f"  {c['anio']}  acierto {wr:>4} (n={c['n']:>5}){marca}")
    print(f"  -> gana en {v['frac_anios_gana']*100:.0f}% de los años con muestra  "
          f"(hace falta >= 60%: {'sí' if v['pasa_anios'] else 'NO'})")

    print("\nPAR POR PAR (top 8):")
    for c in v["por_par"][:8]:
        wr = f"{c['wr']:.0f}%" if c["wr"] is not None else "-"
        print(f"  {c['par']:8} acierto {wr:>4} (n={c['n']:>5})")
    gsm = v["global_sin_mejor"]
    print(f"  -> quitando el mejor par ({v['mejor_par']}): acierto {gsm['wr']}% "
          f"(n={gsm['n']}) límite95 {gsm['low']:.1f}%  "
          f"{'sigue ganando' if v['pasa_amplitud'] else 'SE CAE (era un par)'}")

    print("\n" + "=" * 82)
    if v["robusto"]:
        print(f"EDGE ROBUSTO: {a.exp}m·{a.sesion} pasa Bonferroni, año-por-año y amplitud.")
        print("Siguiente paso: configurar el bot para operar SOLO ese tiempo en esa franja.")
    else:
        falta = []
        if not v["pasa_bonferroni"]:
            falta.append("no supera Bonferroni (posible ruido de multi-comparación)")
        if not v["pasa_anios"]:
            falta.append("no gana en la mayoría de los años")
        if not v["pasa_amplitud"]:
            falta.append("depende de un solo par")
        print("EDGE NO ROBUSTO: " + "; ".join(falta) + ".")
        print("Conclusión honesta: no arriesgar dinero real con esta hipótesis todavía.")
