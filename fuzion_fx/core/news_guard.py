"""
core/news_guard.py (fuzion_fx)
==============================
Motor de BLOQUEO por noticias: durante una ventana de tiempo alrededor de una
noticia de alto impacto, NO se opera (el precio se vuelve erratico y el spread se
dispara). Antes existia el parametro `news_buffer_minutes` pero nadie lo aplicaba;
esto lo aplica.

Fuente: config/news.json (editable por el usuario o por la app), formato:
    {"eventos": [
        {"cuando": "2026-08-12T12:30:00Z", "impacto": "alto",
         "titulo": "US CPI", "monedas": ["USD"]},
        ...]}
- `cuando`: hora UTC del evento (ISO 8601; se acepta la 'Z').
- `impacto`: solo bloquean los "alto" (high). Los demas se ignoran.
- `monedas`: opcional. Si esta, bloquea SOLO los pares que incluyan esa moneda;
  si no, bloquea todos (evento global).

Sin red: el motor solo lee el archivo y compara horas. El feed que LLENA el
archivo (calendario economico) se puede enchufar despues sin tocar esto.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from indicators.pips import currencies_of


def _iso_a_epoch(s: Any) -> Optional[int]:
    """ISO 8601 (con 'Z' o offset) -> epoch segundos UTC. None si no parsea."""
    if not isinstance(s, str) or not s:
        return None
    txt = s.strip().replace("Z", "+00:00")     # 'Z' -> offset UTC explicito
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:                       # sin tz -> se asume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def cargar_eventos(path: str) -> List[Dict[str, Any]]:
    """
    Lee config/news.json y devuelve los eventos con su epoch (`ts`). Robusto: si
    el archivo no existe o esta mal, devuelve [] (sin bloqueo, seguro).
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    crudos = data.get("eventos", []) if isinstance(data, dict) else []
    eventos: List[Dict[str, Any]] = []
    for e in crudos:
        if not isinstance(e, dict):
            continue
        ts = _iso_a_epoch(e.get("cuando"))
        if ts is None:
            continue
        eventos.append({
            "ts": ts,
            "impacto": str(e.get("impacto", "alto")).lower(),
            "titulo": str(e.get("titulo", "noticia")),
            "monedas": [str(m).upper() for m in e.get("monedas", [])
                        if isinstance(m, str)],
        })
    return eventos


def _afecta_al_par(evento: Dict[str, Any], pair: Optional[str]) -> bool:
    """True si el evento afecta a `pair`. Sin `monedas` -> global (afecta a todos).
    Con `monedas` y sin par -> se considera que afecta (bloqueo conservador)."""
    monedas = evento.get("monedas") or []
    if not monedas:
        return True
    if pair is None:
        return True
    par_monedas = currencies_of(pair)
    if par_monedas is None:
        return True                             # par desconocido -> conservador
    return any(m in par_monedas for m in monedas)


def en_bloqueo(now_ts: float, eventos: List[Dict[str, Any]], buffer_min: float,
               pair: Optional[str] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    True (+ el evento) si `now_ts` cae dentro de +/- `buffer_min` de una noticia
    de ALTO impacto que afecte a `pair`. Solo bloquean los de impacto 'alto'.
    """
    ventana = float(buffer_min) * 60.0
    for e in eventos:
        if e.get("impacto") != "alto":
            continue
        if abs(now_ts - e["ts"]) <= ventana and _afecta_al_par(e, pair):
            return True, e
    return False, None


def proximo_evento(now_ts: float, eventos: List[Dict[str, Any]]
                   ) -> Optional[Dict[str, Any]]:
    """El proximo evento de alto impacto (para mostrar en el panel). None si no hay."""
    futuros = [e for e in eventos if e.get("impacto") == "alto" and e["ts"] >= now_ts]
    return min(futuros, key=lambda e: e["ts"]) if futuros else None
