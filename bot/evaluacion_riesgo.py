"""
bot/evaluacion_riesgo.py
========================
EVALUACIÓN DE RIESGO antes de operar (modo evaluación). El borde de reversión gana con
un pico AISLADO (sobre-reacción / barrido de liquidez que corrige). Pero cuando un par
está recibiendo MUCHOS golpes seguidos —lo están martillando, quitando el peso de
arriba/abajo una y otra vez— la reversión FALLA: el precio no se devuelve, sigue siendo
golpeado. Operar ahí es riesgo alto de pérdida.

La idea del trader: detectar esa situación y, si un par está en zona de golpes, NO
tomar sus señales e irse a otra moneda más tranquila ANTES de elegirla.

Cómo se mide (sin unidades raras, robusto): sobre las velas RECIENTES (excluyendo el
pico actual) se cuentan los "golpes" = movimientos grandes respecto al movimiento típico
de ese par. Si hay demasiados, el par está martillado.

Sin red. Test: bot/test_evaluacion_riesgo.py.
"""
from bot.senal_reversion import _pip, PISO_PIPS


def contar_golpes(closes, par, piso_pips=None, n=15):
    """
    Cuenta cuántas de las últimas `n` velas (ANTES del pico actual) fueron un GOLPE: un
    movimiento del tamaño de un pico, es decir >= `piso_pips`. Excluye la última vela (el
    pico que dispara la señal) para medir el RÉGIMEN alrededor, no el propio disparo.

    El piso es el mismo umbral con el que el borde considera "pico". En un mercado
    tranquilo un pico es raro (por eso es señal); si el entorno tiene varios, el par está
    siendo martillado. `piso_pips` lo pone el robot según el tiempo (5m se mueve más que
    1m); por defecto usa el piso base.
    """
    if closes is None or len(closes) < 5:
        return 0
    pip = _pip(par)
    piso = piso_pips if piso_pips is not None else PISO_PIPS
    serie = [float(c) for c in closes]
    ventana = serie[-(n + 1):-1]              # velas previas al pico actual
    if len(ventana) < 3:
        return 0
    moves = [abs(ventana[i] - ventana[i - 1]) / pip for i in range(1, len(ventana))]
    return sum(1 for m in moves if m >= piso)


def en_golpes(closes, par, piso_pips=None, n=15, max_golpes=4):
    """True si el par está en ZONA DE GOLPES (demasiados picos recientes): riesgo alto de
    que la reversión no se dé. En ese caso, no operar y buscar otra moneda."""
    return contar_golpes(closes, par, piso_pips, n) >= int(max_golpes)


if __name__ == "__main__":
    # Mercado tranquilo con UN pico -> pocos golpes (se opera).
    tranquilo = [1.0800 + 0.00005 * ((-1) ** i) for i in range(15)] + [1.0815]
    print("tranquilo golpes:", contar_golpes(tranquilo, "EURCHF"),
          "en_golpes:", en_golpes(tranquilo, "EURCHF"))
    # Mercado martillado: muchos saltos grandes -> muchos golpes (no se opera).
    martillado = [1.0800 + 0.0012 * ((-1) ** i) for i in range(15)] + [1.0815]
    print("martillado golpes:", contar_golpes(martillado, "EURCHF"),
          "en_golpes:", en_golpes(martillado, "EURCHF"))
