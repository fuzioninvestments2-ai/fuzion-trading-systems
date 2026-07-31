"""
bot/tendencia.py
================
FILTRO DE TENDENCIA para la reversión. El borde de reversión apuesta CONTRA el pico
(si la vela subió, apuesta a que baja). Eso funciona cuando el pico es un REBOTE en un
rango, pero es un suicidio cuando el precio va en TENDENCIA y el pico es la tendencia
continuando: apostar en contra de una subida/bajada fuerte pierde.

EL PORQUÉ (lo que fallaba): la confirmación por z-score solo mide si el precio está
"estirado" de su media. En una tendencia SIEMPRE lo está (la media va por detrás), así
que daba luz verde a pelear contra la tendencia. Este filtro lo corrige: mide la
PENDIENTE de las velas ANTERIORES al pico y rechaza la reversión si la tendencia va en
el mismo sentido que el pico (o sea, en contra de la señal).

Medida sin unidades (el pip se cancela): fuerza = pendiente / movimiento_típico. Así
sirve igual para cualquier par y cualquier tiempo. Sin red. Test: test_tendencia.py.
"""
from bot.senal_reversion import CALL, PUT


def _pendiente(y):
    """Pendiente de la recta de mínimos cuadrados de la serie y (precio por vela). Sin
    numpy para no depender de nada. None si hay menos de 2 puntos."""
    n = len(y)
    if n < 2:
        return None
    xm = (n - 1) / 2.0
    ym = sum(y) / n
    num = sum((i - xm) * (y[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    if den == 0:
        return None
    return num / den


def fuerza_tendencia(closes, n=20):
    """
    Fuerza y sentido de la tendencia en las últimas `n` velas ANTES del pico (excluye
    la última, que es el pico). Devuelve un número sin unidades: pendiente por vela
    dividida por el movimiento típico por vela. >0 sube, <0 baja. None si no hay muestra
    o el mercado está totalmente plano.
    """
    if closes is None or len(closes) < 4:
        return None
    serie = [float(c) for c in closes]
    ventana = serie[-(n + 1):-1]          # las n velas previas al pico
    if len(ventana) < 3:
        return None
    difs = sorted(abs(ventana[i] - ventana[i - 1]) for i in range(1, len(ventana)))
    # MEDIANA, no promedio: en una tendencia con volatilidad, un par de picos grandes
    # inflaban el promedio y hacían que la fuerza pareciera baja -> la subida se colaba y
    # el bot le apostaba en contra. La mediana ignora esos picos y detecta la tendencia.
    tipico = difs[len(difs) // 2]
    if tipico == 0:
        tipico = sum(difs) / len(difs)    # respaldo si la mediana es 0 (muchos ceros)
    if tipico == 0:
        return None
    p = _pendiente(ventana)
    if p is None:
        return None
    return p / tipico                     # pendiente normalizada (velas de movimiento típico)


def permite_reversion(closes, direccion, n=20, umbral=0.35):
    """
    True si se PUEDE operar la reversión (la tendencia NO va en el sentido del pico).
    - Señal PUT  (el pico subió): se rechaza si hay tendencia ALCISTA fuerte (fuerza>umbral):
      apostar baja contra una subida es perder.
    - Señal CALL (el pico bajó): se rechaza si hay tendencia BAJISTA fuerte.
    Sin muestra suficiente NO bloquea (se confía en el borde histórico).
    `umbral`: cuánta pendiente normalizada se considera "tendencia" (0.35 ~ deriva clara).
    """
    f = fuerza_tendencia(closes, n)
    if f is None:
        return True
    if direccion == PUT and f > umbral:       # sube fuerte -> no apostar baja
        return False
    if direccion == CALL and f < -umbral:     # baja fuerte -> no apostar alza
        return False
    return True


if __name__ == "__main__":
    sube = [1.0800 + 0.0002 * i for i in range(20)] + [1.0850]   # subida clara + pico arriba
    print("fuerza subida:", round(fuerza_tendencia(sube), 2))
    print("PUT contra subida permitido:", permite_reversion(sube, PUT))   # False
    rango = [1.0800, 1.0802, 1.0799, 1.0801, 1.0800] * 4 + [1.0810]
    print("PUT en rango permitido:", permite_reversion(rango, PUT))       # True
