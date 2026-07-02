"""
bot/chart.py
============
Dibuja el GRÁFICO de velas (como el bot que mostró el usuario) para enviarlo por
Telegram junto a la señal. Estilo oscuro, similar a Pocket Option.

SRP: solo dibuja. Recibe un DataFrame OHLC y guarda un PNG.
Requiere matplotlib (pip install matplotlib).
"""

import matplotlib
matplotlib.use("Agg")          # sin ventana (para servidor/segundo plano)
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def draw_candles(df, asset, tf, path, direccion="", n=40):
    """
    Dibuja las últimas `n` velas del DataFrame (open/high/low/close) y guarda el
    PNG en `path`. Devuelve `path`.
    """
    d = df.tail(n).reset_index(drop=True)
    if len(d) == 0:
        raise ValueError("sin velas para dibujar")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    fig.patch.set_facecolor("#0e1621")
    ax.set_facecolor("#0e1621")

    up, down = "#26a69a", "#ef5350"      # verde / rojo
    for i, row in d.iterrows():
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = up if c >= o else down
        # mecha
        ax.plot([i, i], [l, h], color=color, linewidth=1.0, zorder=1)
        # cuerpo
        alto = abs(c - o) or (h - l) * 0.001 or 1e-9
        ax.add_patch(Rectangle((i - 0.32, min(o, c)), 0.64, alto,
                               color=color, zorder=2))

    titulo = f"{asset}   {tf}"
    if direccion:
        titulo += f"    {direccion}"
    ax.set_title(titulo, color="#e1e8ed", fontsize=12)
    ax.grid(color="#2a3a4a", alpha=0.35, linewidth=0.5)
    ax.tick_params(colors="#8899a6", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a3a4a")
    ax.set_xlim(-1, len(d))
    fig.tight_layout()
    fig.savefig(path, dpi=95, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
