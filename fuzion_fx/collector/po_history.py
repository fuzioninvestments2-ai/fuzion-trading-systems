"""
collector/po_history.py (fuzion_fx)
===================================
Parseo del HISTORIAL que Pocket Option envia por on_history a velas OHLC
normalizadas. Lo dispara `updateHistoryNewFast` (historial reciente al suscribir)
y `loadHistoryPeriod` (escaneo hacia atras).

PORQUE separado: lo usan DOS piezas -> la herramienta de comparacion (Paso 1) y
el colector (Paso 2). Un solo parser evita duplicar la logica (Regla 1) y que las
dos versiones diverjan. El formato exacto de PO no esta documentado oficialmente;
se soportan las dos formas observadas (ver bot/pocket_service.py):

  - VELAS ya hechas: payload["candles"] o payload["data"] = [{time,open,high,low,
    close,volume}, ...] o listas [t, open, close, high, low, (volume)].
  - LINEA de precios: payload["history"] = [[t, precio], ...]. Se agrega a OHLC
    por bucket del periodo (open=primer precio, high=max, low=min, close=ultimo):
    es el precio real que PO dibuja, la fuente de verdad frente al tick ralo.

Sin red. Se prueba con payloads mock.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Vela normalizada: (ts_inicio_seg, open, high, low, close, volume).
Vela = Tuple[int, float, float, float, float, float]


def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def normalizar_ts(t: Any) -> Optional[int]:
    """Epoch a SEGUNDOS enteros. PO a veces manda milisegundos (valor > 1e12)."""
    v = _f(t)
    if v is None:
        return None
    return int(v / 1000) if v > 1e12 else int(v)


def _bucket(ts: int, period: int) -> int:
    """Inicio de vela alineado al periodo (misma convencion que el aggregator)."""
    return ts - (ts % period) if period > 0 else ts


def _vela_de_dict(c: Dict[str, Any]) -> Optional[Vela]:
    """Vela cuando PO la manda como dict {time, open, high, low, close, volume}."""
    t = normalizar_ts(c.get("time", c.get("t", c.get("timestamp"))))
    o = _f(c.get("open", c.get("o")))
    if t is None or o is None:
        return None
    h = _f(c.get("high", c.get("h", o)), o)
    lo = _f(c.get("low", c.get("l", o)), o)
    cl = _f(c.get("close", c.get("c", o)), o)
    vol = _f(c.get("volume", c.get("v", 0)), 0.0)
    return (t, o, h, lo, cl, vol)


def _vela_de_lista(c: Any) -> Optional[Vela]:
    """
    Vela cuando PO la manda como lista. El orden observado en el escaneo hacia
    atras es [t, open, close, high, low, (volume)] (close ANTES que high/low).
    """
    if not isinstance(c, (list, tuple)) or len(c) < 5:
        return None
    t = normalizar_ts(c[0])
    o, cl, h, lo = _f(c[1]), _f(c[2]), _f(c[3]), _f(c[4])
    if t is None or None in (o, cl, h, lo):
        return None
    vol = _f(c[5], 0.0) if len(c) > 5 else 0.0
    return (t, o, h, lo, cl, vol)


def _linea_a_ohlc(hist: List[Any], period: int) -> List[Vela]:
    """
    Agrega la LINEA de precios [[t, precio], ...] a velas OHLC por bucket del
    periodo. open=primer precio del bucket, high=max, low=min, close=ultimo. Es la
    reconstruccion honesta de la vela real desde la serie de cierres de PO.
    """
    agregada: Dict[int, List[float]] = {}
    orden: List[int] = []
    for row in hist:
        try:
            t = normalizar_ts(row[0])
            p = _f(row[1])
        except (IndexError, TypeError):
            continue
        if t is None or p is None:
            continue
        b = _bucket(t, period)
        a = agregada.get(b)
        if a is None:
            agregada[b] = [p, p, p, p]          # open, high, low, close
            orden.append(b)
        else:
            a[1] = max(a[1], p)                  # high
            a[2] = min(a[2], p)                  # low
            a[3] = p                             # close (ultimo)
    return [(b, agregada[b][0], agregada[b][1], agregada[b][2],
             agregada[b][3], 0.0) for b in orden]


def parse_history(payload: Any) -> Optional[Dict[str, Any]]:
    """
    Convierte el payload de on_history a {"asset", "period", "velas"} con `velas`
    en orden CRONOLOGICO, ts alineado al bucket del periodo y sin buckets
    repetidos (el ultimo pisa). Devuelve None si no se pudo interpretar nada.
    """
    if not isinstance(payload, dict):
        return None
    period = int(_f(payload.get("period"), 0) or 0)
    asset = payload.get("asset")

    crudas: List[Vela] = []
    candles = payload.get("candles") or payload.get("data")
    if candles:
        for c in candles:
            v = _vela_de_dict(c) if isinstance(c, dict) else _vela_de_lista(c)
            if v is not None:
                crudas.append(v)
    else:
        crudas = _linea_a_ohlc(payload.get("history") or [], period)

    if not crudas:
        return None

    # Normalizar al bucket del periodo y deduplicar (ultima gana); orden ascendente.
    por_bucket: Dict[int, Vela] = {}
    for (t, o, h, lo, cl, vol) in crudas:
        b = _bucket(int(t), period)
        por_bucket[b] = (b, o, h, lo, cl, vol)
    velas = [por_bucket[b] for b in sorted(por_bucket)]
    return {"asset": asset, "period": period, "velas": velas}
