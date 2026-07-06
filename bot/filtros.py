"""
bot/filtros.py
==============
FILTROS OBLIGATORIOS sobre el veredicto de la sinfonía. La regla del trader es
"el foco es no perder": aunque la alineación diga OPERAR, si un filtro no pasa,
NO se entra.

Filtros:
  - PAYOUT (ambos mercados): <75% no operar; 85-92% peligroso (evitar); 75-85% ok.
  - NOTICIAS (solo real): no operar en la ventana de un evento de alto impacto.
  - SESIÓN (solo real): evitar Asia y NY PM; London/NY son las buenas.
  - SPREAD (solo real): no operar si supera ~2 pips.

Los filtros de real se activan solo si el `sistema` es el real (tiene los marcadores
NOTICIAS_DURANTE / SPREAD_MAX_PIPS). El OTC es 24/7 y de noticias mínimas: solo
aplica payout.

Función PURA: recibe valores (payout, hay_noticia, hora, spread) y decide. Así se
prueba sin red; el que llama calcula esos valores desde NewsFilter/market_hours.

SRP: solo filtra. Sin red. Testeable con asserts.
"""

from bot.alignment import evaluar_alineacion


def _es_real(sistema):
    """El sistema real trae los marcadores de noticias/spread; el OTC no."""
    return getattr(sistema, "NOTICIAS_DURANTE", None) is not None


def clasificar_sesion(hora_est, sistema):
    """
    Devuelve 'evitar' | 'buena' | 'normal' para una hora (EST, 0-24) según las
    ventanas del sistema. Las de 'evitar' mandan.
    """
    def _en(rangos):
        for _, ini, fin in rangos:
            if ini <= hora_est < fin:
                return True
        return False
    if _en(getattr(sistema, "SESIONES_EVITAR", [])):
        return "evitar"
    if _en(getattr(sistema, "SESIONES_BUENAS", [])):
        return "buena"
    return "normal"


def evaluar_filtros(sistema, payout=None, hay_noticia=False, hora_est=None,
                    spread=None):
    """
    Aplica los filtros. Devuelve {'pasa': bool, 'fallos': [str], 'avisos': [str]}.
    Un 'fallo' bloquea la entrada; un 'aviso' no bloquea (informa).
    """
    fallos, avisos = [], []

    # PAYOUT (ambos). SOLO bloquea por debajo de 75% (valor esperado malo). El
    # 85-92% es "inestable" pero el trader OPERA ahí a diario: se AVISA, no bloquea.
    if payout is not None:
        clase = sistema.clasificar_payout(payout)
        if clase == "no_operar":
            fallos.append(f"payout {payout:.0f}% por debajo de 75%")
        elif clase == "aceptable":
            avisos.append(f"payout {payout:.0f}% (zona inestable >85%, pero operable)")

    # Filtros SOLO del mercado real.
    if _es_real(sistema):
        if hay_noticia:
            fallos.append("noticia de alto impacto en la ventana (no operar)")
        if hora_est is not None:
            ses = clasificar_sesion(hora_est, sistema)
            if ses == "evitar":
                fallos.append("sesión a evitar (Asia / NY PM)")
            elif ses == "normal":
                avisos.append("fuera de London/NY (menos movimiento)")
        if not sistema.spread_ok(spread):
            fallos.append(f"spread {spread} > {sistema.SPREAD_MAX_PIPS} pips")

    return {"pasa": not fallos, "fallos": fallos, "avisos": avisos}


def veredicto_final(frames, sistema, payout=None, hay_noticia=False,
                    hora_est=None, spread=None):
    """
    Junta TODO: sinfonía de dirección + filtros. Devuelve el veredicto final.
      - Si la alineación no da OPERAR, ese es el veredicto (no se miran filtros).
      - Si da OPERAR pero un filtro falla -> NO OPERAR (con el motivo del filtro).
      - Si da OPERAR y todo pasa -> OPERAR en la dirección de 1H.
    """
    ali = evaluar_alineacion(frames, sistema)
    if ali["veredicto"] != "OPERAR":
        ali["filtros"] = {"pasa": True, "fallos": [], "avisos": []}
        return ali

    filt = evaluar_filtros(sistema, payout=payout, hay_noticia=hay_noticia,
                           hora_est=hora_est, spread=spread)
    ali["filtros"] = filt
    if not filt["pasa"]:
        ali["veredicto"] = "NO OPERAR"
        ali["motivo"] = "Alineado, pero un filtro lo bloquea: " + \
                        "; ".join(filt["fallos"])
    elif filt["avisos"]:
        ali["motivo"] += "  (" + "; ".join(filt["avisos"]) + ")"
    return ali
