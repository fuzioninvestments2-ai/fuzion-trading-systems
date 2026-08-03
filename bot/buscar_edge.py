"""
bot/buscar_edge.py
==================
BÚSQUEDA DE EDGE REAL (fuera de muestra). Toma todo el historial de datasets/real,
construye la tabla SOLO con el tramo de entrenamiento (60%) y corre el pipeline en vivo
sobre el tramo de prueba (40%). De cada operación real guarda su HORA (sesión de mercado)
y el TAMAÑO del pico, y luego corta por esas condiciones para ver si ALGÚN subconjunto
—una sesión, un tamaño de pico, un par/tiempo— tiene ventaja REAL con margen estadístico.

Por qué el margen estadístico: un 56% con 40 señales no es edge, es ruido. El margen 95%
(±1.96·√(p(1-p)/n)) dice cuánto puede caer el acierto por azar. Solo declara GANA una
celda si el LÍMITE INFERIOR (acierto − margen) supera el equilibrio Y hay muestra
suficiente (>= MIN_N). Así no nos engañamos con un número alto de pocas operaciones.

No borra ni modifica nada: solo lee el historial. Sin red. Test: bot/test_buscar_edge.py.

Uso:
    PYTHONPATH=. python bot/buscar_edge.py                 # todos los pares reales
    PYTHONPATH=. python bot/buscar_edge.py EURUSD GBPUSD   # solo esos
    PYTHONPATH=. python bot/buscar_edge.py --pago 92 --min-n 200
"""
import math

from bot.simulacion import simular_ops
from bot.senal_reversion import PISO_PIPS

# Sesiones de mercado por hora UTC. El FX se mueve distinto según quién opera: la reversión
# tras pico puede tener más o menos borde según la liquidez de la sesión.
SESIONES = (
    ("Asia",          lambda h: 23 <= h or h < 7),
    ("Londres",       lambda h: 7 <= h < 12),
    ("Solape LDN-NY", lambda h: 12 <= h < 16),
    ("Nueva York",    lambda h: 16 <= h < 21),
    ("Cierre",        lambda h: 21 <= h < 23),
)

MIN_N = 200          # por debajo, la muestra no da para afirmar nada (es ruido)


def _wilson_low(wins, n, z=1.96):
    """Límite inferior del intervalo de Wilson al 95% (en %). Más honesto que la normal
    con muestras chicas: nunca da por debajo de 0 ni por encima de 100, y no infla el borde.
    Es la cota inferior REAL del acierto: si esto supera el equilibrio, hay edge de verdad."""
    if n == 0:
        return 0.0
    p = wins / n
    z2 = z * z
    centro = (p + z2 / (2 * n)) / (1 + z2 / n)
    radio = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n)
    return round(max(0.0, centro - radio) * 100, 1)


def _celda(ops, equilibrio, min_n=MIN_N):
    """Resume una lista de ops en {n, wins, wr, low, gana}. `gana` solo si el límite inferior
    (Wilson 95%) supera el equilibrio con muestra suficiente."""
    n = len(ops)
    wins = sum(1 for o in ops if o["gana"])
    low = _wilson_low(wins, n)
    return {"n": n, "wins": wins,
            "wr": (round(wins / n * 100, 1) if n else None),
            "low": low,
            "gana": bool(n >= min_n and low > equilibrio)}


def buscar(ops_por_par, payout=85.0, min_n=MIN_N):
    """Dado {par: {exp: [ops...]}}, corta por par/tiempo, por SESIÓN y por TAMAÑO de pico
    (juntando todos los pares) y devuelve las celdas con su acierto y margen.
    Devuelve {"por_par_tiempo": [...], "por_sesion": [...], "por_pico": [...], "ganadoras": [...]}."""
    equilibrio = 100.0 / (1.0 + payout / 100.0)
    por_par_tiempo, por_sesion, por_pico, ganadoras = [], [], [], []

    # Todas las ops juntas por tiempo (para cortar por sesión y por pico con muestra grande).
    todas = {}
    for par, por_exp in ops_por_par.items():
        for exp, ops in por_exp.items():
            todas.setdefault(exp, []).extend(ops)
            c = _celda(ops, equilibrio, min_n)
            fila = {"par": par, "exp": exp, **c}
            por_par_tiempo.append(fila)
            if c["gana"]:
                ganadoras.append({"tipo": "par/tiempo", "clave": f"{par} {exp}m", **c})

    for exp, ops in sorted(todas.items()):
        for nombre, test in SESIONES:
            sub = [o for o in ops if test(o["hora"])]
            c = _celda(sub, equilibrio, min_n)
            fila = {"exp": exp, "sesion": nombre, **c}
            por_sesion.append(fila)
            if c["gana"]:
                ganadoras.append({"tipo": "sesión", "clave": f"{exp}m · {nombre}", **c})

    # Tamaño de pico relativo al piso: los picos grandes fueron el único borde observado.
    for exp, ops in sorted(todas.items()):
        tramos = (("pico chico", PISO_PIPS, PISO_PIPS * 1.5),
                  ("pico medio", PISO_PIPS * 1.5, PISO_PIPS * 2.5),
                  ("pico grande", PISO_PIPS * 2.5, float("inf")))
        for nombre, lo, hi in tramos:
            sub = [o for o in ops if lo <= o["pico"] < hi]
            c = _celda(sub, equilibrio, min_n)
            fila = {"exp": exp, "tramo": nombre, "rango": f"[{lo:g},{hi:g})", **c}
            por_pico.append(fila)
            if c["gana"]:
                ganadoras.append({"tipo": "pico", "clave": f"{exp}m · {nombre}", **c})

    return {"por_par_tiempo": por_par_tiempo, "por_sesion": por_sesion,
            "por_pico": por_pico, "ganadoras": ganadoras, "equilibrio": round(equilibrio, 1)}


def _ops_test(df, par, tiempos, payout, frac_test=0.4):
    """Construye la tabla con el 60% de entrenamiento y devuelve {exp: [ops del test 40%]}."""
    import numpy as np
    from bot.tabla_reversion import tabla_par
    df = df.sort_values("timestamp")
    ts = df["timestamp"].astype("int64").tolist()
    cl = df["close"].astype(float).tolist()
    corte_train = int(len(cl) * 0.6)
    corte_test = int(len(cl) * (1 - frac_test))
    train = np.asarray(cl[:corte_train], dtype=float)   # tabla_par vectoriza con numpy
    ts_test, cl_test = ts[corte_test:], cl[corte_test:]
    out = {}
    for e in tiempos:
        tr = tabla_par(train, par, e)
        tabla = {par: {str(e): [[u, wr] for u, wr, _ in tr]}} if tr else {par: {}}
        out[e] = simular_ops(ts_test, cl_test, par, e, tabla, payout=payout)
    return out


if __name__ == "__main__":
    import argparse
    import glob
    import os
    import pandas as pd

    ap = argparse.ArgumentParser(description="Busca edge real OOS por sesión y tamaño de pico.")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = todos los reales)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--pago", type=float, default=85.0)
    ap.add_argument("--min-n", type=int, default=MIN_N)
    a = ap.parse_args()

    TIEMPOS = (1, 2, 3, 5)
    # Acepta datasets/real/*__M1.csv.gz y, si no hay, datasets/*__M1.csv.gz (nube de prueba).
    rutas = [r for r in sorted(glob.glob(f"{a.destino}/*__M1.csv.gz"))
             if "_otc" not in os.path.basename(r).lower()]
    if not rutas:
        rutas = [r for r in sorted(glob.glob("datasets/*__M1.csv.gz"))
                 if "_otc" not in os.path.basename(r).lower()]
    if a.pares:
        rutas = [r for r in rutas if os.path.basename(r).split("__")[0] in a.pares]

    equi = 100.0 / (1.0 + a.pago / 100.0)
    print(f"BÚSQUEDA DE EDGE OOS  ·  pago {a.pago:.0f}%  ·  equilibrio {equi:.1f}%  ·  "
          f"muestra mínima {a.min_n}  ·  {len(rutas)} pares")
    print("GANA una celda solo si el LÍMITE INFERIOR 95% (Wilson) supera el equilibrio con "
          "muestra suficiente. Un acierto alto de pocas señales NO cuenta: es ruido.")
    print("=" * 78)

    ops_por_par = {}
    total = len(rutas)
    for idx, r in enumerate(rutas, 1):
        par = os.path.basename(r).split("__")[0]
        # Avisa ANTES de procesar: con 23 años cada par tarda; sin esto el usuario ve la
        # pantalla quieta minutos y cree que se colgó. El "..." se queda hasta que termina.
        print(f"  [{idx}/{total}] {par:8} leyendo y evaluando ...", end="", flush=True)
        try:
            df = pd.read_csv(r)
        except Exception as e:
            print(f" ERROR {e}", flush=True)
            continue
        ops_por_par[par] = _ops_test(df, par, TIEMPOS, a.pago)
        tot = sum(len(v) for v in ops_por_par[par].values())
        print(f" {len(df)} velas -> {tot} operaciones", flush=True)

    res = buscar(ops_por_par, a.pago, a.min_n)

    def _tabla(titulo, filas, cols):
        print("\n" + titulo)
        for f in filas:
            wr = f"{f['wr']:.0f}%" if f["wr"] is not None else "-"
            marca = "  <<< GANA" if f["gana"] else ""
            clave = "  ".join(str(f[c]) for c in cols)
            print(f"  {clave:28} acierto {wr:>5} (n={f['n']:>5})  límite95 {f['low']:>5.1f}%"
                  f"  (equilibrio {res['equilibrio']}%){marca}")

    _tabla("POR SESIÓN DE MERCADO (todos los pares juntos):", res["por_sesion"], ("exp", "sesion"))
    _tabla("POR TAMAÑO DE PICO (todos los pares juntos):", res["por_pico"], ("exp", "tramo"))

    print("\n" + "=" * 78)
    if res["ganadoras"]:
        print(f"EDGE ENCONTRADO en {len(res['ganadoras'])} subconjunto(s):")
        for g in res["ganadoras"]:
            print(f"  · {g['tipo']:10} {g['clave']:22} acierto {g['wr']:.1f}% "
                  f"(n={g['n']}) límite95 {g['low']:.1f}% > equilibrio {res['equilibrio']}%")
        print("Estos son los ÚNICOS subconjuntos donde operar tiene ventaja real medida.")
    else:
        print("SIN EDGE: ningún subconjunto (par/tiempo, sesión ni tamaño de pico) supera el "
              f"equilibrio {res['equilibrio']}% con margen estadístico y muestra >= {a.min_n}.")
        print("Conclusión honesta: con estos filtros la reversión NO tiene ventaja explotable. "
              "Solo demo — no dinero real.")
