"""
bot/news_filter.py
==================
FILTRO DE NOTICIAS para el bot REAL (solo monedas). El mercado real se descontrola
en noticias de alto impacto (NFP, tipos, IPC...): las velas se disparan y la
lectura técnica deja de valer. Este filtro CALLA al bot en esa ventana. Es
PROTECCIÓN, no predicción — el objetivo del proyecto: disciplina, no adivinar.

Fuente: calendario económico PÚBLICO de faireconomy (ForexFactory), en JSON:
  https://nfs.faireconomy.media/ff_calendar_thisweek.json
Es un feed abierto y gratuito; no hay scraping ni evasión.

Regla (de la guía del usuario): bloquear 15 min ANTES y DESPUÉS de cada evento
de impacto alto/crítico, para la(s) moneda(s) afectada(s). Un par se bloquea si
CUALQUIERA de sus dos monedas tiene un evento en la ventana.

SRP: solo decide si se puede operar por noticias. La descarga es opcional y
defensiva (si falla la red, NO bloquea de más: sigue con la caché o permite).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

URL_CALENDARIO = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Ventana de bloqueo alrededor del evento (minutos antes y después).
VENTANA_MIN = 15

# Impactos que bloquean. FF usa "High"/"Medium"/"Low"/"Holiday".
IMPACTOS_BLOQUEO = {"high", "critical"}


def _a_dt(valor) -> Optional[datetime]:
    """Convierte el campo de fecha del feed a datetime con zona (UTC si falta)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_eventos(texto: str) -> List[Dict]:
    """
    Parsea el JSON del calendario a una lista de eventos normalizados:
    {'moneda': 'USD', 'impacto': 'high', 'dt': datetime}. Testeable SIN red.
    Ignora entradas sin moneda, sin fecha válida o sin impacto.
    """
    eventos: List[Dict] = []
    try:
        datos = json.loads(texto)
    except (ValueError, TypeError):
        return eventos
    if not isinstance(datos, list):
        return eventos
    for e in datos:
        if not isinstance(e, dict):
            continue
        moneda = (e.get("country") or e.get("currency") or "").strip().upper()
        impacto = str(e.get("impact", "")).strip().lower()
        dt = _a_dt(e.get("date") or e.get("datetime") or e.get("time"))
        if not moneda or dt is None or not impacto:
            continue
        eventos.append({"moneda": moneda, "impacto": impacto, "dt": dt})
    return eventos


def _monedas_del_par(asset: str) -> Set[str]:
    """
    Extrae las dos monedas de un par ('EURUSD' -> {'EUR','USD'}). Tolera barras y
    minúsculas ('eur/usd'). Un par estándar son 6 letras (dos ISO de 3).
    """
    limpio = asset.replace("/", "").replace("_otc", "").strip().upper()
    if len(limpio) >= 6:
        return {limpio[:3], limpio[3:6]}
    return set()


class NewsFilter:
    """
    Mantiene la lista de eventos y decide si un par se puede operar AHORA.

    Uso:
        nf = NewsFilter()
        nf.cargar(texto_json)          # o nf.actualizar() para bajarlo de la red
        if nf.can_trade("EURUSD"): ...
    """

    def __init__(self, ventana_min: int = VENTANA_MIN, logger=None):
        self.ventana = timedelta(minutes=int(ventana_min))
        self.log = logger or logging.getLogger("news_filter")
        self._eventos: List[Dict] = []
        self._ultima_actualizacion: Optional[datetime] = None

    def cargar(self, texto: str) -> int:
        """Carga eventos desde texto JSON (sin red). Devuelve cuántos válidos."""
        self._eventos = parse_eventos(texto)
        return len(self._eventos)

    def monedas_bloqueadas(self, ahora: Optional[datetime] = None) -> Set[str]:
        """Monedas con un evento de alto impacto dentro de la ventana de `ahora`."""
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        elif ahora.tzinfo is None:
            ahora = ahora.replace(tzinfo=timezone.utc)
        bloqueadas: Set[str] = set()
        for ev in self._eventos:
            if ev["impacto"] not in IMPACTOS_BLOQUEO:
                continue
            if abs(ahora - ev["dt"]) <= self.ventana:
                bloqueadas.add(ev["moneda"])
        return bloqueadas

    def can_trade(self, asset: str, ahora: Optional[datetime] = None) -> bool:
        """
        True si el par se puede operar (ninguna de sus monedas está en ventana de
        noticia alta). Los OTC son sintéticos: no dependen de noticias reales, así
        que NUNCA se bloquean por este filtro.
        """
        if asset.endswith("_otc"):
            return True
        bloqueadas = self.monedas_bloqueadas(ahora)
        return not (_monedas_del_par(asset) & bloqueadas)

    def proximo_evento(self, asset: str,
                       ahora: Optional[datetime] = None) -> Optional[Dict]:
        """Devuelve el evento de alto impacto más próximo que afecta al par (info)."""
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        elif ahora.tzinfo is None:
            ahora = ahora.replace(tzinfo=timezone.utc)
        monedas = _monedas_del_par(asset)
        futuros = [e for e in self._eventos
                   if e["impacto"] in IMPACTOS_BLOQUEO
                   and e["moneda"] in monedas and e["dt"] >= ahora]
        return min(futuros, key=lambda e: e["dt"]) if futuros else None

    def actualizar(self, url: str = URL_CALENDARIO, timeout: float = 15.0) -> int:
        """
        Descarga el calendario y carga los eventos. DEFENSIVO: si la red falla,
        conserva los eventos que ya tenía (no bloquea de más ni rompe). Devuelve
        cuántos eventos hay cargados tras el intento.
        """
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                texto = r.read().decode("utf-8", "replace")
            n = self.cargar(texto)
            self._ultima_actualizacion = datetime.now(timezone.utc)
            self.log.info("Calendario de noticias: %d eventos.", n)
            return n
        except Exception as exc:
            self.log.warning("No se pudo actualizar el calendario (%s). "
                             "Sigo con %d eventos en caché.", exc, len(self._eventos))
            return len(self._eventos)
