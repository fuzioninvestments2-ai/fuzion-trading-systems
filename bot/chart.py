"""
bot/chart.py
============
Dibuja el GRÁFICO de velas del MERCADO REAL (FX) para enviarlo por Telegram con la
señal. Estilo limpio de plataforma de trading (fondo oscuro, precios a la derecha,
precio actual marcado). Solo mercado real: aquí no hay nada de OTC.

SRP: solo dibuja. Recibe un DataFrame OHLC y guarda un PNG.
Requiere matplotlib (pip install matplotlib).
"""

import matplotlib
matplotlib.use("Agg")          # sin ventana (para servidor/segundo plano)
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from datetime import datetime, timedelta

# Paleta tipo plataforma real (verde/rojo suaves sobre fondo azul-noche).
FONDO = "#0e1621"
REJILLA = "#1c2b3a"
EJE = "#5b6b7a"
TEXTO = "#d5dee6"
VERDE = "#26a69a"
ROJO = "#ef5350"
LINEA_PRECIO = "#e1b000"       # línea del precio actual (ámbar)


def _etiquetas_hora(d, ahora=None):
    """
    Calcula (posiciones, etiquetas) de hora para el eje X.

    EL PORQUÉ de anclar a AHORA: los timestamps de Pocket Option vienen en la zona
    horaria del bróker y no coincidían con el reloj del usuario. En un gráfico en
    vivo, la vela de la DERECHA es "ahora"; así que ponemos la última vela = hora
    actual del usuario y retrocedemos por el intervalo entre velas. Resultado: las
    horas SIEMPRE cuadran con su reloj.

    `ahora`: datetime de referencia (por defecto datetime.now, la hora local del
    usuario). Parametrizable para poder probarlo sin depender del reloj.
    """
    n = len(d)
    if n == 0:
        return None, None
    intervalo = 60.0
    if "timestamp" in d.columns and n >= 2:
        ts = [int(x) for x in d["timestamp"]]
        difs = [(b - a) / 1000.0 for a, b in zip(ts, ts[1:]) if b > a]
        if difs:
            intervalo = min(difs)
    fmt = "%H:%M:%S" if intervalo < 60 else "%H:%M"
    ref = ahora or datetime.now()
    paso = max(1, n // 7)
    pos = list(range(0, n, paso))
    lab = [(ref - timedelta(seconds=(n - 1 - i) * intervalo)).strftime(fmt)
           for i in pos]
    return pos, lab


def draw_candles(df, asset, tf, path, direccion="", n=40, levels=None):
    """
    Dibuja las últimas `n` velas del DataFrame (open/high/low/close) y guarda el PNG en
    `path`. Devuelve `path`. Estilo plataforma real: precios a la derecha, hora abajo,
    precio ACTUAL marcado con una línea, y el sentido (CALL/PUT) en el título.

    levels: dict opcional {soportes:[...], resistencias:[...]} para techo/piso.
    """
    d = df.tail(n).reset_index(drop=True)
    if len(d) == 0:
        raise ValueError("sin velas para dibujar")

    fig, ax = plt.subplots(figsize=(11.5, 5.2))
    fig.patch.set_facecolor(FONDO)
    ax.set_facecolor(FONDO)

    for i, row in d.iterrows():
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = VERDE if c >= o else ROJO
        ax.plot([i, i], [l, h], color=color, linewidth=1.0, zorder=1)     # mecha
        alto = abs(c - o) or (h - l) * 0.001 or 1e-9                       # cuerpo
        ax.add_patch(Rectangle((i - 0.32, min(o, c)), 0.64, alto,
                               color=color, zorder=2))

    # Líneas de SOPORTE (piso, verde) y RESISTENCIA (techo, rojo).
    if levels:
        for r in levels.get("resistencias", []):
            ax.axhline(r, color=ROJO, linestyle="--", linewidth=0.8, alpha=0.5, zorder=0)
        for s in levels.get("soportes", []):
            ax.axhline(s, color=VERDE, linestyle="--", linewidth=0.8, alpha=0.5, zorder=0)

    # PRECIO ACTUAL: línea horizontal + etiqueta a la derecha (como una plataforma real).
    precio = float(d["close"].iloc[-1])
    sube = precio >= float(d["open"].iloc[-1])
    col_precio = VERDE if sube else ROJO
    ax.axhline(precio, color=LINEA_PRECIO, linestyle=":", linewidth=0.9, alpha=0.8, zorder=3)
    dec = 3 if precio >= 10 else 5          # JPY (2-3 dec) vs resto (5 dec)
    ax.annotate(f"{precio:.{dec}f}", xy=(len(d) - 1, precio), xytext=(6, 0),
                textcoords="offset points", va="center", ha="left", fontsize=9,
                color="#0e1621", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", fc=col_precio, ec="none"))

    # Título con MARCA FUZION FX + par + tiempo + sentido.
    flecha = "▼ PUT" if direccion == "PUT" else ("▲ CALL" if direccion == "CALL" else "")
    col_dir = ROJO if direccion == "PUT" else VERDE
    ax.set_title(f"FUZION FX   ·   {asset}   ·   {tf}", color=TEXTO, fontsize=12,
                 fontweight="bold", loc="left")
    if flecha:
        ax.set_title(flecha, color=col_dir, fontsize=12, fontweight="bold", loc="right")

    ax.grid(color=REJILLA, alpha=0.6, linewidth=0.5)
    ax.tick_params(colors=EJE, labelsize=8)
    for s in ax.spines.values():
        s.set_color(REJILLA)

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")

    pos, lab = _etiquetas_hora(d)
    if pos is not None:
        ax.set_xticks(pos)
        ax.set_xticklabels(lab, rotation=0)

    ax.set_xlim(-1, len(d) + 3)             # aire a la derecha para la etiqueta de precio
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path
