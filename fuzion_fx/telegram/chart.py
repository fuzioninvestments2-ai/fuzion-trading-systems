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


def render_candles(candles: Dict[str, Sequence[float]], title: str,
                   direction: str = "", n: int = 40) -> Optional[io.BytesIO]:
    """
    PNG de las ultimas `n` velas. `direction` (CALL/PUT) solo colorea el titulo.
    Devuelve BytesIO listo para send_photo, o None si faltan datos.
    """
    o = list(candles.get("open", []))[-n:]
    h = list(candles.get("high", []))[-n:]
    l = list(candles.get("low", []))[-n:]
    c = list(candles.get("close", []))[-n:]
    if len(c) < 5:
        return None

    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=100)
    fig.patch.set_facecolor("#0e1116")
    ax.set_facecolor("#0e1116")

    for i in range(len(c)):
        sube = c[i] >= o[i]
        color = "#26a69a" if sube else "#ef5350"     # verde / rojo
        # Mecha (high-low)
        ax.plot([i, i], [l[i], h[i]], color=color, linewidth=0.8, zorder=1)
        # Cuerpo (open-close)
        alto = abs(c[i] - o[i]) or (h[i] - l[i]) * 0.02 or 1e-9
        base = min(o[i], c[i])
        ax.add_patch(plt.Rectangle((i - 0.3, base), 0.6, alto, color=color, zorder=2))

    # Ultimo precio como linea/etiqueta.
    ult = c[-1]
    ax.axhline(ult, color="#888", linewidth=0.6, linestyle="--", zorder=0)
    ax.annotate(f"{ult:.5f}", xy=(len(c) - 1, ult), xytext=(4, 0),
                textcoords="offset points", color="#eee", fontsize=8,
                va="center")

    ax.set_title(title, color="#eee", fontsize=10, loc="left")
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
