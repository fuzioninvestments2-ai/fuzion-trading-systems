"""
scripts/analisis_visual.py (fuzion_fx)
======================================
PANEL VISUAL del acierto REAL: junta las señales ya resueltas de los 4 bots
(data/db/f*_memory.db) y dibuja DONDE se pierde, para ver el patron del error:

  1) Win-rate por SETUP        -> que combinacion de indicadores falla.
  2) Win-rate por TIMEFRAME    -> si 1m/2m/3m/5m es peor.
  3) Win-rate por HORA (local) -> si una sesion (Asia/Londres/NY) es peor.
  4) Win-rate por PAR          -> que divisa arrastra la perdida.
  5) Acierto ACUMULADO en el tiempo -> si empeora/mejora.

Cada barra lleva su n (muestra) y una linea de BREAK-EVEN (~54%): por debajo, no da
plata aunque parezca alto. Con muestra chica el numero es RUIDO (se marca).

Guarda data/analisis_visual.png (se abre solo si se corre con --abrir).
Uso:  python fuzion_fx/scripts/analisis_visual.py [--abrir] [--min 5]
Test: fuzion_fx/tests/test_analisis_visual.py (sin red).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core.config import ROOT                                    # noqa: E402

BOTS = [("f1_m1", "1m"), ("f2_m2", "2m"), ("f3_m3", "3m"), ("f4_m5", "5m")]
BREAK_EVEN = 54.0                       # referencia (~pago 85%); linea guia
_VERDE = "#26a69a"
_ROJO = "#ef5350"
_GRIS = "#888888"


def cargar_resueltas() -> List[Dict[str, Any]]:
    """Todas las señales resueltas (win/loss) de los 4 bots, con par/tf/setup/hora."""
    filas: List[Dict[str, Any]] = []
    for bot_id, tf in BOTS:
        p = os.path.join(ROOT, "data", "db", f"{bot_id}_memory.db")
        if not os.path.exists(p):
            continue
        try:
            conn = sqlite3.connect(p)
            cur = conn.execute(
                "SELECT pair, setup_id, result, ts, entry_show_ts FROM signals "
                "WHERE resolved=1 AND result IN ('win','loss')")
            for pair, setup, result, ts, show in cur.fetchall():
                base_ts = show if show is not None else ts
                hora = datetime.fromtimestamp(int(base_ts)).astimezone().hour
                filas.append({"tf": tf, "pair": pair, "setup": setup,
                              "result": result, "ts": int(ts), "hora": hora})
            conn.close()
        except sqlite3.Error:
            continue
    return sorted(filas, key=lambda r: r["ts"])


def _wr(sub: List[Dict[str, Any]]):
    w = sum(1 for r in sub if r["result"] == "win")
    n = len(sub)
    return (w / n * 100.0 if n else 0.0), n


def _por(filas, clave):
    g: Dict[Any, List[Dict[str, Any]]] = {}
    for r in filas:
        g.setdefault(r[clave], []).append(r)
    return g


def _barras(ax, datos, titulo, min_n, orden=None):
    """datos: {etiqueta: [filas]}. Barra=win-rate; color verde/rojo vs break-even;
    gris si muestra < min_n (ruido). Etiqueta con n."""
    items = list(datos.items())
    if orden:
        items.sort(key=lambda kv: orden.index(kv[0]) if kv[0] in orden else 999)
    else:
        items.sort(key=lambda kv: _wr(kv[1])[0])
    etiquetas, valores, colores, textos = [], [], [], []
    for et, sub in items:
        wr, n = _wr(sub)
        etiquetas.append(str(et))
        valores.append(wr)
        if n < min_n:
            colores.append(_GRIS)
        else:
            colores.append(_VERDE if wr >= BREAK_EVEN else _ROJO)
        textos.append(f"{wr:.0f}% (n={n})")
    y = range(len(etiquetas))
    ax.barh(list(y), valores, color=colores)
    ax.set_yticks(list(y))
    ax.set_yticklabels(etiquetas, fontsize=7)
    ax.axvline(BREAK_EVEN, color="#ffca28", linewidth=1.0, linestyle="--")
    ax.axvline(50, color="#555", linewidth=0.8, linestyle=":")
    ax.set_xlim(0, 100)
    ax.set_title(titulo, fontsize=9, color="#ddd", loc="left")
    for i, t in enumerate(textos):
        ax.text(2, i, t, va="center", fontsize=6, color="#fff")
    ax.tick_params(colors="#999", labelsize=7)


def graficar(filas: List[Dict[str, Any]], out_path: str, min_n: int = 5) -> str:
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), dpi=100)
    fig.patch.set_facecolor("#0e1116")
    for ax in axes.flat:
        ax.set_facecolor("#0e1116")
        for s in ax.spines.values():
            s.set_color("#333")

    wr_glob, n_glob = _wr(filas)
    fig.suptitle(f"FUZION FX · Donde se pierde · GLOBAL {wr_glob:.1f}%  "
                 f"(n={n_glob} · break-even ~{BREAK_EVEN:.0f}%)",
                 color=_VERDE if wr_glob >= BREAK_EVEN else _ROJO, fontsize=13)

    if not filas:
        for ax in axes.flat:
            ax.text(0.5, 0.5, "Sin señales resueltas todavia\n(deja correr el bot)",
                    ha="center", va="center", color="#aaa", transform=ax.transAxes)
        axes.flat[0].set_title("Aun sin datos", color="#ddd")
    else:
        _barras(axes[0][0], _por(filas, "setup"), "Por SETUP (que falla)", min_n)
        _barras(axes[0][1], _por(filas, "tf"), "Por TIEMPO", min_n,
                orden=["1m", "2m", "3m", "5m"])
        _barras(axes[0][2], _por(filas, "pair"), "Por PAR", min_n)
        _barras(axes[1][0], _por(filas, "hora"), "Por HORA (local)", min_n)
        # Acumulado en el tiempo
        ax = axes[1][1]
        acc, wins = [], 0
        for i, r in enumerate(filas, 1):
            wins += 1 if r["result"] == "win" else 0
            acc.append(wins / i * 100.0)
        ax.plot(range(1, len(acc) + 1), acc, color=_VERDE, linewidth=1.3)
        ax.axhline(BREAK_EVEN, color="#ffca28", linewidth=1.0, linestyle="--")
        ax.axhline(50, color="#555", linewidth=0.8, linestyle=":")
        ax.set_ylim(0, 100)
        ax.set_title("Acierto ACUMULADO (orden de emision)", fontsize=9,
                     color="#ddd", loc="left")
        ax.tick_params(colors="#999", labelsize=7)
        # Panel resumen (texto)
        ax = axes[1][2]
        ax.axis("off")
        w = sum(1 for r in filas if r["result"] == "win")
        peor_setup = min(_por(filas, "setup").items(),
                         key=lambda kv: _wr(kv[1])[0] if _wr(kv[1])[1] >= min_n else 999,
                         default=(None, []))
        lineas = [f"Total resueltas: {n_glob}",
                  f"WIN: {w}   LOSS: {n_glob - w}",
                  f"Win-rate: {wr_glob:.1f}%",
                  f"Break-even ref: {BREAK_EVEN:.0f}%",
                  ""]
        if peor_setup[0] is not None:
            pw, pn = _wr(peor_setup[1])
            lineas.append(f"Peor setup (n>={min_n}):")
            lineas.append(f"  {peor_setup[0]}")
            lineas.append(f"  {pw:.0f}%  (n={pn})")
        lineas += ["", "Verde = supera break-even",
                   "Rojo = pierde  ·  Gris = poca muestra"]
        ax.text(0.02, 0.98, "\n".join(lineas), va="top", ha="left",
                color="#eee", fontsize=9, family="monospace",
                transform=ax.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Panel visual: donde pierde el bot.")
    ap.add_argument("--min", type=int, default=5, help="muestra minima por barra")
    ap.add_argument("--abrir", action="store_true", help="abre el PNG al terminar")
    args = ap.parse_args()
    filas = cargar_resueltas()
    out = os.path.join(ROOT, "data", "analisis_visual.png")
    graficar(filas, out, min_n=args.min)
    print(f"Panel guardado en: {out}")
    print(f"Señales resueltas analizadas: {len(filas)}")
    if not filas:
        print("Aun no hay resueltas: deja correr el bot con el mercado abierto.")
    if args.abrir:
        try:
            os.startfile(out)                          # Windows
        except AttributeError:
            pass


if __name__ == "__main__":
    main()
