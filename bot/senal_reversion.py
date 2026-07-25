"""
bot/senal_reversion.py
======================
LA MÁQUINA (núcleo). Genera la señal sobre el ÚNICO borde que el historial de 23 años
confirmó fuera de muestra: REVERSIÓN TRAS PICO. Si la última vela de 1m se movió mucho
en un solo paso, el precio tiende a DEVOLVERSE; se opera en contra del pico.

La confianza NO es inventada: es el win-rate REAL fuera de muestra medido en
`backtest_reversion_real` sobre datasets/real (2003→hoy, split train/test). Cuanto más
grande el pico, mayor el acierto y el P&L — por eso la confianza sube por tramo.

Regla del piso: por debajo de 4 pips el borde (~52-53%) casi no cubre el break-even de
92% de payout, así que NO se opera; el valor está en los picos grandes. Picos > 20
pips se descartan (posible error de dato / evento anómalo).

Este módulo NO conecta a red ni opera: solo decide la señal a partir de velas ya
recibidas. Test: bot/test_senal_reversion.py.
"""
CALL = "CALL"
PUT = "PUT"
PAYOUT = 0.92
BREAKEVEN = 100.0 / (1.0 + PAYOUT)          # 52.08%
PISO_PIPS = 4                                # por debajo: borde insuficiente -> no operar
MAX_PIPS = 20                                # por encima: probable error/anomalía -> no operar

# Tramos (pico mínimo en pips -> win-rate % OOS a 3m) medidos en el backtest real.
# El bot usa el tramo MÁS ALTO cuyo umbral no supera el pico observado.
TABLA_OOS = ((4, 53.5), (5, 54.0), (6, 54.6), (8, 56.1), (10, 57.5))


def _pip(par):
    """Tamaño del pip: pares con JPY a 2 decimales, el resto a 4."""
    return 0.01 if par.upper().endswith("JPY") else 0.0001


def _prob_por_pico(pips):
    """Win-rate OOS del tramo correspondiente al tamaño del pico. None si < piso."""
    prob = None
    for umbral, wr in TABLA_OOS:
        if pips >= umbral:
            prob = wr
    return prob


def _pnl_op(win_rate):
    """P&L esperado por operación (%) con payout 92% para un win-rate en %."""
    p = win_rate / 100.0
    return (p * PAYOUT - (1 - p)) * 100.0


def senal(closes, par, expiry_min=3):
    """
    Decide la señal de reversión a partir de los cierres de 1m recientes.

    closes    : lista/array de cierres M1 en orden cronológico (usa los 2 últimos).
    par       : p.ej. 'EURUSD' (define el tamaño del pip).
    expiry_min: minutos de la opción (el borde es estable de 1 a 10m).

    Devuelve dict con: operar (bool), direccion (CALL/PUT), pips, probabilidad,
    pnl_esperado, expiry_min, motivo.
    """
    base = {"operar": False, "direccion": None, "pips": 0.0, "probabilidad": None,
            "pnl_esperado": None, "expiry_min": expiry_min, "par": par}
    if closes is None or len(closes) < 2:
        return {**base, "motivo": "faltan velas (se necesitan al menos 2 de 1m)"}
    pip = _pip(par)
    mov = (float(closes[-1]) - float(closes[-2])) / pip     # pips de la última vela, con signo
    magnitud = abs(mov)
    base["pips"] = round(mov, 1)

    if magnitud < PISO_PIPS:
        return {**base, "motivo": f"pico chico ({magnitud:.1f} pips < {PISO_PIPS}): "
                                  f"el borde no cubre el payout, no se opera"}
    if magnitud > MAX_PIPS:
        return {**base, "motivo": f"pico anómalo ({magnitud:.1f} pips > {MAX_PIPS}): "
                                  f"posible error de dato, no se opera"}

    prob = _prob_por_pico(magnitud)
    # Reversión: si la vela SUBIÓ (mov>0) apostamos a que BAJA (PUT), y viceversa.
    direccion = PUT if mov > 0 else CALL
    hacia = "subió" if mov > 0 else "bajó"
    return {**base, "operar": True, "direccion": direccion,
            "probabilidad": prob, "pnl_esperado": round(_pnl_op(prob), 2),
            "motivo": f"la vela {hacia} {magnitud:.1f} pips; se espera reversión "
                      f"({direccion}). Acierto histórico fuera de muestra: {prob:.1f}%"}


if __name__ == "__main__":
    # Demostración rápida con cierres de ejemplo (sin red).
    ejemplos = [
        ("EURUSD", [1.1000, 1.1006]),      # subió 6 pips -> PUT
        ("EURUSD", [1.1000, 1.09920]),     # bajó 8 pips -> CALL
        ("USDJPY", [150.00, 150.05]),      # subió 5 pips (JPY) -> PUT
        ("EURUSD", [1.1000, 1.10015]),     # 1.5 pips -> no opera
    ]
    for par, closes in ejemplos:
        s = senal(closes, par)
        print(f"{par}: {s['motivo']}")
