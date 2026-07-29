"""
bot/autocorrector.py
====================
El CORRECTOR de señales: evita que el error de un par se ARRASTRE a las demás
señales. Antes de enviar, mira el acierto REAL reciente de ESE par+tiempo (lo que
mide `SignalTracker`, no el backtest) y decide si vale la pena mandarla.

EL PORQUÉ (matemática de la opción binaria):
  Con un pago `p` (fracción, 72% -> 0.72), a largo plazo solo se gana si el acierto
  supera el punto de equilibrio:
        break-even = 1 / (1 + p)
  Con p=0.72 -> 0.581 (hay que acertar > 58.1%). Si un par+tiempo viene acertando
  por DEBAJO de ese umbral en sus últimas señales reales, seguir enviándolo es
  perder seguro: se SILENCIA ese par+tiempo (no otros).

Honestidad: esto NO predice mejor una señal suelta; corta la sangría de un par que
dejó de tener ventaja. El par se silencia solo y se re-activa solo cuando su
acierto reciente vuelve a superar el equilibrio (la sombra se sigue registrando).

Sin red: pura aritmética sobre lo que ya guardó el tracker. Test: test_autocorrector.py.
"""


def break_even(payout_pct):
    """Punto de equilibrio (acierto mínimo) para un pago dado en %. 72 -> 0.581."""
    p = float(payout_pct) / 100.0
    if p <= 0:
        return 1.0                      # sin pago, imposible: exige acierto perfecto
    return 1.0 / (1.0 + p)


def debe_enviar(win_rate, muestra, payout_pct, min_muestra=20, margen=0.0):
    """
    Decide si una señal de un par+tiempo se ENVÍA al usuario.

    win_rate  : acierto reciente REAL (0-1) o None si aún no hay señales resueltas.
    muestra   : cuántas señales resueltas respaldan ese win_rate.
    payout_pct: pago del activo en % (define el punto de equilibrio).
    min_muestra: hasta juntar esta muestra NO se silencia (no hay evidencia todavía;
                 se confía en el borde del backtest para no quedar mudo al arrancar).
    margen    : exigencia extra sobre el equilibrio (0.03 = pedir 3 puntos más).

    Devuelve (enviar: bool, motivo: str).
    """
    umbral = break_even(payout_pct) + float(margen)
    if win_rate is None or muestra < int(min_muestra):
        # Sin evidencia en vivo suficiente: se respeta el borde histórico y se envía,
        # pero se sigue midiendo para poder silenciar cuando haya muestra.
        return True, f"sin muestra suficiente ({muestra}/{min_muestra}): se confía en el histórico"
    if win_rate < umbral:
        return False, (f"silenciado: acierto reciente {win_rate*100:.0f}% < equilibrio "
                       f"{umbral*100:.0f}% en las últimas {muestra}")
    return True, f"acierto reciente {win_rate*100:.0f}% >= equilibrio {umbral*100:.0f}%"


if __name__ == "__main__":
    # Con pago 72% el equilibrio es 58.1%.
    print("break-even 72% =", round(break_even(72), 3))
    print(debe_enviar(0.50, 30, 72))     # 50% < 58% -> NO enviar
    print(debe_enviar(0.65, 30, 72))     # 65% >= 58% -> enviar
    print(debe_enviar(0.40, 5, 72))      # poca muestra -> enviar (se confía histórico)
