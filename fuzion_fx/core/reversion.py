"""
core/reversion.py (fuzion_fx)
=============================
GENERADOR DE REVERSION TRAS PICO — port fiel de `bot/senal_reversion.py` al paquete
fuzion_fx (los procesos de fuzion_fx solo ponen fuzion_fx/ en sys.path, no la raiz,
asi que no pueden importar `bot.*` en runtime; por eso se porta, con la MISMA tabla
OOS medida sobre 23 anios de historial real).

Es el UNICO borde que el historial confirmo fuera de muestra: si la ultima vela de 1m
se movio mucho en un solo paso, el precio tiende a DEVOLVERSE; se opera EN CONTRA del
pico. La confianza por tramo (TABLA_OOS) es win-rate REAL fuera de muestra, no inventado.

No conecta a red ni opera: decide la senal a partir de velas ya recibidas.
Test: fuzion_fx/tests/test_reversion.py.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence

CALL = "CALL"
PUT = "PUT"
PAYOUT = 0.92
BREAKEVEN = 100.0 / (1.0 + PAYOUT)          # 52.08%
PISO_PIPS = 4                                # por debajo: borde insuficiente -> no operar
MAX_PIPS = 20                                # por encima: probable error/anomalia -> no operar

# Tramos (pico minimo en pips -> win-rate % OOS a 3m) medidos en el backtest real de
# 23 anios. El bot usa el tramo MAS ALTO cuyo umbral no supera el pico observado.
TABLA_OOS = ((4, 53.5), (5, 54.0), (6, 54.6), (8, 56.1), (10, 57.5))


def _pip(par: str) -> float:
    """Tamano del pip: pares con JPY a 2 decimales, el resto a 4."""
    return 0.01 if par.upper().endswith("JPY") else 0.0001


def cargar_tabla(ruta: str) -> Dict[str, Any]:
    """Carga la tabla de reversion por par (reversion_tabla.json). {} si no existe."""
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _prob_por_pico(pips: float, buckets=TABLA_OOS) -> Optional[float]:
    """Win-rate OOS del tramo (umbral, wr) mas alto cuyo umbral no supera el pico.
    None si el pico no alcanza ningun tramo."""
    prob = None
    for umbral, wr in sorted(buckets):
        if pips >= umbral:
            prob = wr
    return prob


def _pnl_op(win_rate: float) -> float:
    """P&L esperado por operacion (%) con payout 92% para un win-rate en %."""
    p = win_rate / 100.0
    return (p * PAYOUT - (1 - p)) * 100.0


def senal(closes: Optional[Sequence[float]], par: str, expiry_min: int = 3,
          tabla: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Decide la senal de reversion a partir de los cierres de 1m recientes.

    closes    : cierres M1 en orden cronologico (usa los 2 ultimos).
    par       : p.ej. 'EURUSD' (define el tamano del pip).
    expiry_min: minutos de la opcion (el borde es estable de 1 a 10m).
    tabla     : dict {par: [[umbral, wr], ...]} por par. None -> tabla global OOS.

    Devuelve: operar (bool), direccion (CALL/PUT), pips, probabilidad, pnl_esperado,
    expiry_min, motivo.
    """
    base = {"operar": False, "direccion": None, "pips": 0.0, "probabilidad": None,
            "pnl_esperado": None, "expiry_min": expiry_min, "par": par}
    if closes is None or len(closes) < 2:
        return {**base, "motivo": "faltan velas (se necesitan al menos 2 de 1m)"}
    pip = _pip(par)
    mov = (float(closes[-1]) - float(closes[-2])) / pip     # pips de la ultima vela, con signo
    magnitud = abs(mov)
    base["pips"] = round(mov, 1)

    # Tabla del par (por tiempo o plana) o global. Si el par tiene tabla pero no borde a
    # ESTE tiempo, no se opera (no se cae a otro tiempo: evita disparar 1m con criterio 3m).
    t = tabla.get(par) if tabla else None
    if isinstance(t, dict):
        buckets = t.get(str(expiry_min))
        if not buckets:
            return {**base, "motivo": f"{par} sin borde medido a {expiry_min}m; no se opera"}
    elif isinstance(t, list) and t:
        buckets = t
    else:
        buckets = TABLA_OOS

    # Piso/techo del pico salen de la tabla medida (cada tiempo tiene picos de otro tamano).
    cap_anomalia = MAX_PIPS * math.sqrt(max(1, int(expiry_min)))
    if buckets is TABLA_OOS:
        # TABLA_OOS medida a 3m -> se escala relativo a 3m (sqrt(exp/3)).
        esc = math.sqrt(max(1, int(expiry_min)) / 3.0)
        piso, techo = PISO_PIPS * esc, MAX_PIPS * esc
    else:
        umbrales = [u for u, _ in buckets]
        piso, techo = min(umbrales), min(max(umbrales) * 3, cap_anomalia)

    if magnitud < piso:
        return {**base, "motivo": f"pico chico ({magnitud:.1f} pips < {piso:g}): "
                                  f"el borde no cubre el payout, no se opera"}
    if magnitud > techo:
        return {**base, "motivo": f"pico anomalo ({magnitud:.1f} pips > {techo:g}): "
                                  f"posible error de dato, no se opera"}

    prob = _prob_por_pico(magnitud, buckets)
    if prob is None:
        return {**base, "motivo": f"pico de {magnitud:.1f} pips sin borde medido en "
                                  f"{par}, no se opera"}
    # Reversion: si la vela SUBIO (mov>0) apostamos a que BAJA (PUT), y viceversa.
    direccion = PUT if mov > 0 else CALL
    hacia = "subio" if mov > 0 else "bajo"
    return {**base, "operar": True, "direccion": direccion,
            "probabilidad": prob, "pnl_esperado": round(_pnl_op(prob), 2),
            "motivo": f"la vela {hacia} {magnitud:.1f} pips; se espera reversion "
                      f"({direccion}). Acierto historico fuera de muestra: {prob:.1f}%"}
