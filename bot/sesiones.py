"""
bot/sesiones.py
===============
Sesiones del mercado FX por hora UTC, para mostrar en la tarjeta en qué mercado estás
operando (Sídney / Tokio / Londres / Nueva York) y sus solapes. El solape
Londres+Nueva York (13:00–17:00 UTC) es el de más volumen.

Horas UTC de cada sesión (aprox., estándar del mercado):
  - Sídney      : 22:00 – 07:00
  - Tokio       : 00:00 – 09:00
  - Londres     : 08:00 – 17:00
  - Nueva York  : 13:00 – 22:00

Sin red. Test: bot/test_sesiones.py.
"""

# (nombre, hora_inicio_utc, hora_fin_utc). Si fin < inicio, cruza medianoche.
SESIONES = (
    ("Sídney", 22, 7),
    ("Tokio", 0, 9),
    ("Londres", 8, 17),
    ("Nueva York", 13, 22),
)


def _activa(inicio, fin, hora):
    """True si `hora` (0-23) cae dentro de [inicio, fin), tolerando cruce de medianoche."""
    if inicio <= fin:
        return inicio <= hora < fin
    return hora >= inicio or hora < fin           # cruza medianoche (p.ej. Sídney)


def sesiones_activas(hora_utc):
    """Lista de nombres de sesiones abiertas a esa hora UTC (0-23)."""
    h = int(hora_utc) % 24
    return [nombre for nombre, ini, fin in SESIONES if _activa(ini, fin, h)]


def etiqueta(hora_utc):
    """Texto corto de las sesiones activas, p.ej. 'Londres + Nueva York'. 'Cerrado' si
    ninguna (raro en FX salvo fin de semana)."""
    activas = sesiones_activas(hora_utc)
    if not activas:
        return "Cerrado"
    # Prioriza mostrar las grandes (Londres/NY) primero si están.
    orden = {"Londres": 0, "Nueva York": 1, "Tokio": 2, "Sídney": 3}
    activas.sort(key=lambda n: orden.get(n, 9))
    return " + ".join(activas)


if __name__ == "__main__":
    for h in (2, 9, 14, 20, 23):
        print(f"{h:02d}:00 UTC -> {etiqueta(h)}")
