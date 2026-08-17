"""
telegram/chart.py (fuzion_fx)
=============================
Dibuja un grafico de velas (candlestick) en PNG, en memoria (BytesIO), para
mandarlo como foto en la tarjeta de Telegram. Sin ventana (backend Agg).

Entrada: dict {open, high, low, close} con listas cronologicas.
Salida:  BytesIO con el PNG, o None si no hay datos suficientes.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")                       # sin GUI: seguro en cualquier entorno
import matplotlib.pyplot as plt             # noqa: E402


_VERDE = "#26a69a"
_ROJO = "#ef5350"


def render_candles(candles: Dict[str, Sequence[float]], title: str,
                   direction: str = "", n: int = 40,
                   entry_price: Optional[float] = None,
                   entry_show_ts: Optional[int] = None,
                   tf_seconds: Optional[int] = None) -> Optional[io.BytesIO]:
    """
    PNG de las ultimas `n` velas COORDINADO con la senal: marca la DIRECCION
    (flecha ARRIBA para CALL, ABAJO para PUT) en el borde derecho, donde entra la
    operacion, y dibuja la linea de ENTRADA (`entry_price`) para que el grafico
    diga lo mismo que la tarjeta. `direction` colorea el titulo y la flecha.
    Devuelve BytesIO listo para send_photo, o None si faltan datos.
    """
    o = list(candles.get("open", []))[-n:]
    h = list(candles.get("high", []))[-n:]
    l = list(candles.get("low", []))[-n:]
    c = list(candles.get("close", []))[-n:]
    if len(c) < 5:
        return None

    dir_norm = str(direction).upper()
    col_dir = _VERDE if dir_norm == "CALL" else (_ROJO if dir_norm == "PUT" else "#eee")

    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=100)
    fig.patch.set_facecolor("#0e1116")
    ax.set_facecolor("#0e1116")

    for i in range(len(c)):
        sube = c[i] >= o[i]
        color = _VERDE if sube else _ROJO            # verde / rojo
        # Mecha (high-low)
        ax.plot([i, i], [l[i], h[i]], color=color, linewidth=0.8, zorder=1)
        # Cuerpo (open-close)
        alto = abs(c[i] - o[i]) or (h[i] - l[i]) * 0.02 or 1e-9
        base = min(o[i], c[i])
        ax.add_patch(plt.Rectangle((i - 0.3, base), 0.6, alto, color=color, zorder=2))

    # Linea de ENTRADA (precio con el que se dispara la senal): coordina el
    # grafico con la tarjeta. Si no se pasa, cae al ultimo cierre.
    ref = float(entry_price) if entry_price is not None else c[-1]
    ax.axhline(ref, color=col_dir, linewidth=0.9, linestyle="--", zorder=0)
    ax.annotate(f"{ref:.5f}", xy=(len(c) - 1, ref), xytext=(4, 0),
                textcoords="offset points", color=col_dir, fontsize=8, va="center")

    # Flecha de DIRECCION en el borde derecho (donde entra la operacion): CALL
    # apunta ARRIBA, PUT ABAJO. Es la coordinacion visual con la senal.
    if dir_norm in ("CALL", "PUT"):
        x = len(c) - 1
        rango = (max(h) - min(l)) or 1e-9
        dy = rango * 0.18
        if dir_norm == "CALL":
            y0, y1, etiqueta = ref - dy, ref, "CALL ▲"
        else:
            y0, y1, etiqueta = ref + dy, ref, "PUT ▼"
        ax.annotate("", xy=(x, y1), xytext=(x, y0),
                    arrowprops=dict(arrowstyle="-|>", color=col_dir, linewidth=2))
        ax.text(0.015, 0.94, etiqueta, transform=ax.transAxes, color=col_dir,
                fontsize=10, fontweight="bold", va="top")

    # EJE DE TIEMPO (hora local): antes el eje X era solo indice de vela -> el
    # grafico "no tenia hora". Con entry_show_ts (borde LOCAL de la vela de entrada)
    # y tf se etiqueta cada vela con su HORA real: la ultima vela dibujada es la
    # recien cerrada (entry_show - tf) y hacia atras -tf. Asi el grafico dice la
    # MISMA hora que la tarjeta, sin desfase de PO.
    if entry_show_ts is not None and tf_seconds:
        from datetime import datetime
        m = len(c)
        # hora de la vela i = entrada - tf*(m - i)  (i=m-1 -> entrada - tf)
        idx = list(range(0, m, max(1, m // 6)))          # ~6 marcas
        ax.set_xticks(idx)
        ax.set_xticklabels(
            [datetime.fromtimestamp(
                int(entry_show_ts) - int(tf_seconds) * (m - i)).astimezone().strftime("%H:%M")
             for i in idx], rotation=0)
        # Marca la vela de ENTRADA (la siguiente al ultimo cierre) al borde derecho.
        ent_h = datetime.fromtimestamp(int(entry_show_ts)).astimezone().strftime("%H:%M")
        ax.text(0.985, 0.06, f"entrada {ent_h}", transform=ax.transAxes,
                color=col_dir, fontsize=8, ha="right", va="bottom")

    ax.set_title(title, color=col_dir, fontsize=10, loc="left")
    ax.tick_params(colors="#888", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#333")
    ax.margins(x=0.02)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf
