"""
src/market/economic_calendar.py
===============================
FASE 2: calendario economico BASICO (filtro defensivo de noticias high-impact).

Proposito: cerca de un evento de alto impacto el precio FX se vuelve erratico y
manipulable; el bot debe CALLAR (no dar senal) en esa ventana. Es proteccion,
no prediccion.

Alcance honesto:
  - Solo MERCADO REAL (FX). En OTC el precio es sintetico de PO y estos eventos
    NO aplican -> is_news_event siempre False.
  - Un par se ve afectado si CUALQUIERA de sus dos divisas tiene evento
    (EURUSD se frena por eventos de EUR o de USD).

Modelo de eventos (dos tipos):
  1. RECURRENTE por regla, cuando la regla es real y verificable:
     - USD NFP: primer viernes de cada mes, 13:30 UTC (8:30 ET aprox).
  2. AGENDADO (fecha explicita), para lo que NO tiene regla mensual limpia:
     decisiones de tasa (FOMC/ECB/BOE/BOJ) y publicaciones (CPI/PMI). La agenda
     de abajo es BEST-EFFORT y debe verificarse/actualizarse contra la fuente
     oficial (ForexFactory / investing.com). Ante la duda, es preferible callar
     de mas: bloquear una senal no cuesta, entrar en una noticia si.

Ventana de bloqueo: [evento - minutes_after, evento + minutes_before]. Por
defecto se bloquea desde 60 min ANTES hasta 15 min DESPUES (el pico de
volatilidad suele ser justo tras el dato).

Funciones sin red y con `now` inyectable: se prueban sin internet ni reloj real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.indicators.pips import currencies_of


@dataclass(frozen=True)
class NewsEvent:
    currency: str          # divisa afectada (USD/EUR/GBP/JPY...)
    name: str              # NFP, FOMC, CPI, ECB, PMI, BOE, BOJ...
    dt_utc: datetime       # momento del evento (aware, UTC)


# --- Agenda explicita (BEST-EFFORT 2026 — VERIFICAR con fuente oficial) --------
# Formato: (divisa, nombre, "YYYY-MM-DDTHH:MM" en UTC). Decisiones de tasa y
# datos sin regla mensual limpia. Reemplazar por el calendario real del ano.
_SCHEDULE_RAW = [
    # USD FOMC (decisiones de tasa, 19:00 UTC aprox)
    ("USD", "FOMC", "2026-01-28T19:00"), ("USD", "FOMC", "2026-03-18T18:00"),
    ("USD", "FOMC", "2026-04-29T18:00"), ("USD", "FOMC", "2026-06-17T18:00"),
    ("USD", "FOMC", "2026-07-29T18:00"), ("USD", "FOMC", "2026-09-16T18:00"),
    ("USD", "FOMC", "2026-10-28T18:00"), ("USD", "FOMC", "2026-12-09T19:00"),
    # USD CPI (inflacion, 13:30 UTC aprox, mediados de mes)
    ("USD", "CPI", "2026-01-13T13:30"), ("USD", "CPI", "2026-02-11T13:30"),
    ("USD", "CPI", "2026-03-11T12:30"), ("USD", "CPI", "2026-04-10T12:30"),
    ("USD", "CPI", "2026-05-13T12:30"), ("USD", "CPI", "2026-06-10T12:30"),
    # EUR ECB (decisiones de tasa, 12:15 UTC aprox)
    ("EUR", "ECB", "2026-01-29T13:15"), ("EUR", "ECB", "2026-03-12T13:15"),
    ("EUR", "ECB", "2026-04-16T12:15"), ("EUR", "ECB", "2026-06-04T12:15"),
    ("EUR", "ECB", "2026-07-16T12:15"), ("EUR", "ECB", "2026-09-10T12:15"),
    # EUR PMI (flash, 09:00 UTC aprox, ~3a semana)
    ("EUR", "PMI", "2026-01-23T09:00"), ("EUR", "PMI", "2026-02-20T09:00"),
    ("EUR", "PMI", "2026-03-23T09:00"), ("EUR", "PMI", "2026-04-23T08:00"),
    # GBP BOE (decisiones de tasa, 12:00 UTC aprox)
    ("GBP", "BOE", "2026-02-05T12:00"), ("GBP", "BOE", "2026-03-19T12:00"),
    ("GBP", "BOE", "2026-05-07T11:00"), ("GBP", "BOE", "2026-06-18T11:00"),
    ("GBP", "BOE", "2026-08-06T11:00"), ("GBP", "BOE", "2026-09-17T11:00"),
    # JPY BOJ (decisiones de tasa, 03:00 UTC aprox)
    ("JPY", "BOJ", "2026-01-23T03:00"), ("JPY", "BOJ", "2026-03-19T03:00"),
    ("JPY", "BOJ", "2026-04-28T03:00"), ("JPY", "BOJ", "2026-06-16T03:00"),
    ("JPY", "BOJ", "2026-07-29T03:00"), ("JPY", "BOJ", "2026-09-18T03:00"),
]


def _parse(raw) -> NewsEvent:
    cur, name, ts = raw
    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return NewsEvent(cur, name, dt)


def nfp_for_month(year: int, month: int, hora_utc: int = 13,
                  minuto_utc: int = 30) -> datetime:
    """
    NFP = primer viernes del mes a las 13:30 UTC (regla real). weekday(): lun=0..
    vie=4; el primer dia 1..7 cuyo weekday sea viernes.
    """
    for day in range(1, 8):
        d = datetime(year, month, day, hora_utc, minuto_utc, tzinfo=timezone.utc)
        if d.weekday() == 4:                 # viernes
            return d
    raise RuntimeError("mes sin viernes en los primeros 7 dias (imposible)")


class EconomicCalendar:
    def __init__(self, events: Optional[List[NewsEvent]] = None) -> None:
        # Eventos agendados (fecha explicita). Los recurrentes (NFP) se generan
        # al vuelo segun la ventana consultada.
        self.scheduled: List[NewsEvent] = events if events is not None else [
            _parse(r) for r in _SCHEDULE_RAW]

    def _nfp_en_ventana(self, ini: datetime, fin: datetime) -> List[NewsEvent]:
        """NFP del mes de `ini` y del mes de `fin` (por si la ventana cruza mes)."""
        meses = {(ini.year, ini.month), (fin.year, fin.month)}
        out = []
        for (y, m) in meses:
            d = nfp_for_month(y, m)
            if ini <= d <= fin:
                out.append(NewsEvent("USD", "NFP", d))
        return out

    def upcoming(self, pair: str, now: datetime, minutes_before: int = 60,
                 minutes_after: int = 15, is_otc: bool = False) -> List[NewsEvent]:
        """
        Eventos high-impact que afectan al par dentro de la ventana de bloqueo.
        OTC -> lista vacia (no aplica). No-FX -> vacia.
        """
        if is_otc:
            return []
        cur = currencies_of(pair)
        if cur is None:
            return []
        divisas = set(cur)

        ini = now - timedelta(minutes=minutes_after)
        fin = now + timedelta(minutes=minutes_before)

        candidatos = list(self.scheduled) + self._nfp_en_ventana(ini, fin)
        return [e for e in candidatos
                if e.currency in divisas and ini <= e.dt_utc <= fin]

    def is_news_event(self, pair: str, now: datetime, minutes_before: int = 60,
                      minutes_after: int = 15, is_otc: bool = False) -> bool:
        """True si hay algun evento high-impact para el par en la ventana."""
        return len(self.upcoming(pair, now, minutes_before, minutes_after, is_otc)) > 0
