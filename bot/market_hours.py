"""
bot/market_hours.py
===================
Horario de mercado.

  - Activos OTC (terminan en "_otc"): abiertos 24/7 (Pocket Option los ofrece
    también fines de semana).
  - Activos REALES (forex, acciones): solo de lunes a viernes (horario forex).
    Cerrado el fin de semana.

⚠️ Honestidad: los DÍAS FESTIVOS concretos NO se controlan aquí (varían por país
y año). Esto cubre el caso principal (fin de semana). Se puede ampliar luego con
un calendario de festivos si hace falta.

SRP: solo dice si el mercado está abierto. No opera. La hora se puede inyectar
(para pruebas deterministas).
"""

from datetime import datetime, timezone


def is_open(asset_code, now=None):
    """
    Devuelve (abierto: bool, motivo: str).
    `now`: datetime en UTC (si no se pasa, usa la hora actual).
    """
    if asset_code.endswith("_otc"):
        return True, "OTC (24/7)"

    now = now or datetime.now(timezone.utc)
    wd = now.weekday()          # 0=lunes ... 5=sábado, 6=domingo
    h = now.hour

    # El forex abre domingo ~22:00 UTC y cierra viernes ~22:00 UTC.
    if wd == 5:                                   # sábado
        return False, "mercado real CERRADO (sábado)"
    if wd == 6 and h < 22:                        # domingo antes de la apertura
        return False, "mercado real CERRADO (domingo)"
    if wd == 4 and h >= 22:                       # viernes tras el cierre
        return False, "mercado real CERRADO (viernes noche)"
    return True, "mercado real abierto"
