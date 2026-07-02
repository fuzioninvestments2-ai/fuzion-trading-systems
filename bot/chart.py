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
from datetime import datetime


def _etiquetas_hora(d):
    """
    Calcula (posiciones, etiquetas) de hora para el eje X a partir de la columna
    'timestamp' (ms). Muestra ~7 marcas repartidas. Si las velas son de menos de
    un minuto usa HH:MM:SS; si no, HH:MM. Devuelve (None, None) si no hay hora.
    """
    if "timestamp" not in d.columns or len(d) == 0:
        return None, None
    ts = [int(x) for x in d["timestamp"]]
    # Intervalo típico entre velas (para decidir el formato de hora).
    difs = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    intervalo = min(difs) if difs else 60000
    fmt = "%H:%M:%S" if intervalo < 60000 else "%H:%M"
    paso = max(1, len(d) // 7)
    pos = list(range(0, len(d), paso))
    # datetime.fromtimestamp usa la hora LOCAL de la máquina (la del usuario),
    # así la hora del gráfico coincide con su reloj.
    lab = [datetime.fromtimestamp(ts[i] / 1000.0).strftime(fmt) for i in pos]
    return pos, lab


def draw_candles(df, asset, tf, path, direccion="", n=40, levels=None):
    """
    Dibuja las últimas `n` velas del DataFrame (open/high/low/close) y guarda el
    PNG en `path`. Devuelve `path`.

    Estilo Pocket Option: precios a la DERECHA, hora abajo, fondo oscuro.

    levels: dict opcional {soportes: [...], resistencias: [...]} para dibujar
            líneas de techo (resistencia, roja) y piso (soporte, verde).
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

    # Líneas de SOPORTE (piso, verde) y RESISTENCIA (techo, rojo): zonas donde
    # el precio suele rebotar o rechazar. Ayudan a ver "techo y piso" de un vistazo.
    if levels:
        for r in levels.get("resistencias", []):
            ax.axhline(r, color="#ef5350", linestyle="--", linewidth=0.8,
                       alpha=0.6, zorder=0)
        for s in levels.get("soportes", []):
            ax.axhline(s, color="#26a69a", linestyle="--", linewidth=0.8,
                       alpha=0.6, zorder=0)

    titulo = f"{asset}   {tf}"
    if direccion:
        titulo += f"    {direccion}"
    ax.set_title(titulo, color="#e1e8ed", fontsize=12)
    ax.grid(color="#2a3a4a", alpha=0.35, linewidth=0.5)
    ax.tick_params(colors="#8899a6", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a3a4a")

    # PRECIOS a la DERECHA (como Pocket Option): más natural para leer el precio
    # actual, que está al borde derecho del gráfico.
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")

    # HORA en el eje X (en vez de números de vela) para que se lea como una
    # plataforma real.
    pos, lab = _etiquetas_hora(d)
    if pos is not None:
        ax.set_xticks(pos)
        ax.set_xticklabels(lab, rotation=0)

    ax.set_xlim(-1, len(d))
    fig.tight_layout()
    fig.savefig(path, dpi=95, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
