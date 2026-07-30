"""
bot/confirmacion_reversion.py
=============================
CONFIRMACIÓN de la reversión antes de enviar. El borde de `senal_reversion` mira solo
el PICO de la última vela. Esto añade una segunda lectura barata: ¿el precio está
ESTIRADO de su media reciente en el sentido del pico?

EL PORQUÉ (mean-reversion): la reversión es probable cuando el precio se alejó de su
media (extensión), no cuando el pico es el ARRANQUE de una tendencia. Se mide con el
z-score del último cierre contra la media/desviación de la ventana previa:
        z = (cierre - media) / desviación
  - Pico ARRIBA (PUT): se confirma si z >= z_min (precio muy por encima de su media).
  - Pico ABAJO (CALL): se confirma si z <= -z_min (muy por debajo).
Si no hay muestra o la desviación es 0, NO bloquea (se confía en el borde histórico):
mejor no quedar mudo por falta de datos al arrancar.

Sin red, sin dependencias externas (aritmética pura). Test: test_confirmacion_reversion.py.
"""
from bot.senal_reversion import CALL, PUT


def z_score(closes, n=20):
    """
    z-score del ÚLTIMO cierre contra la media/desviación de los `n` cierres previos
    (excluye el propio último para no contaminar la media con el pico). None si no hay
    muestra suficiente o la desviación es 0.
    """
    if closes is None or len(closes) < 3:
        return None
    serie = [float(c) for c in closes]
    ventana = serie[-(n + 1):-1]                 # los n previos al último
    if len(ventana) < 2:
        return None
    media = sum(ventana) / len(ventana)
    var = sum((x - media) ** 2 for x in ventana) / len(ventana)
    desv = var ** 0.5
    if desv == 0:
        return None
    return (serie[-1] - media) / desv


def confirma(closes, direccion, z_min=1.0, n=20):
    """
    True si la reversión está confirmada por la extensión del precio (o si no hay
    muestra para medir: no bloquea). `direccion` es la de la señal (CALL/PUT).
    """
    z = z_score(closes, n)
    if z is None:
        return True                              # sin datos: se confía en el borde
    if direccion == PUT:                         # pico arriba: confirmar sobre-extensión alta
        return z >= z_min
    if direccion == CALL:                        # pico abajo: confirmar sobre-extensión baja
        return z <= -z_min
    return True


if __name__ == "__main__":
    # Subida estirada -> confirma PUT; en medio de la nube -> no confirma.
    sube = [1.0800] * 20 + [1.0815]
    print("z sube:", round(z_score(sube), 2), "confirma PUT:", confirma(sube, PUT))
    plano = [1.0800, 1.0801, 1.0799, 1.0800, 1.08005]
    print("confirma PUT plano:", confirma(plano, PUT))
