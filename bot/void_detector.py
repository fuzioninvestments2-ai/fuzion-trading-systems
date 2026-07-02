"""
bot/void_detector.py
=====================
Detecta el "VACÍO DEL MERCADO": huecos o silencio en el flujo de precios.

El usuario pidió "saber detectar el vacío del mercado". OJO: esto NO es lo mismo
que "mercado plano".
  - PLANO   = llegan ticks, pero el precio casi no cambia (poco movimiento).
  - VACÍO   = NO llegan ticks (o llegan con huecos): el feed se congeló, el
              activo dejó de cotizar, o hubo un salto temporal. Operar sobre un
              feed con vacío es peligroso: la última vela está incompleta o vieja
              y cualquier "señal" se calcula sobre datos muertos.

EL PORQUÉ de mirar el TIEMPO entre ticks (no el precio): un vacío se nota porque
el reloj avanza pero no entran precios nuevos. En OTC de Pocket Option los ticks
llegan ~cada segundo; un silencio de varios segundos es anómalo.

SRP: solo detecta. Recibe ticks [(ts_segundos, precio), ...] y opina. Sin red.
"""


def detect_void(ticks, now=None, stale_max=8.0, gap_max=6.0,
                min_density=0.25, window=120):
    """
    Analiza los últimos `window` segundos de ticks y decide si hay VACÍO.

    ticks       : lista [(ts_segundos, precio), ...] en orden cronológico.
    now         : timestamp actual (segundos). Si None, usa el último tick
                  (así el test es determinista sin reloj).
    stale_max   : segundos máximos desde el último tick antes de considerar el
                  feed "viejo" (congelado ahora mismo).
    gap_max     : hueco máximo permitido ENTRE dos ticks consecutivos dentro de
                  la ventana; uno mayor = el feed se cayó un rato.
    min_density : ticks por segundo mínimos esperados; por debajo hay silencio.
    window      : segundos hacia atrás que se examinan.

    Devuelve dict: {void: bool, reasons: [str], staleness: float,
                    max_gap: float, density: float}.
    """
    res = {"void": False, "reasons": [], "staleness": 0.0,
           "max_gap": 0.0, "density": 0.0}
    if not ticks or len(ticks) < 2:
        # Sin datos suficientes es, en la práctica, un vacío (no hay flujo).
        res["void"] = True
        res["reasons"].append("sin flujo de precios (pocos o ningún tick)")
        return res

    ts = [float(t) for t, _ in ticks]
    last = ts[-1]
    ref = float(now) if now is not None else last

    # Recortamos a la ventana reciente para no arrastrar huecos antiguos.
    recientes = [t for t in ts if t >= ref - window]
    if len(recientes) < 2:
        recientes = ts[-2:]

    # 1) STALENESS: ¿cuánto hace del último tick respecto a "ahora"?
    staleness = max(0.0, ref - last)
    res["staleness"] = round(staleness, 2)
    if staleness > stale_max:
        res["void"] = True
        res["reasons"].append(
            f"feed congelado: {staleness:.1f}s sin precios nuevos")

    # 2) HUECO INTERNO: mayor separación entre dos ticks consecutivos.
    max_gap = 0.0
    for a, b in zip(recientes, recientes[1:]):
        d = b - a
        if d > max_gap:
            max_gap = d
    res["max_gap"] = round(max_gap, 2)
    if max_gap > gap_max:
        res["void"] = True
        res["reasons"].append(
            f"hueco en el flujo: {max_gap:.1f}s sin datos entre ticks")

    # 3) DENSIDAD: ticks por segundo en la ventana. Poco flujo = silencio.
    span = max(1e-9, recientes[-1] - recientes[0])
    density = (len(recientes) - 1) / span
    res["density"] = round(density, 3)
    if density < min_density:
        res["void"] = True
        res["reasons"].append(
            f"flujo escaso: {density:.2f} ticks/s (mercado casi sin actividad)")

    return res
