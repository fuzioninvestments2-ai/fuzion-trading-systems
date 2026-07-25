"""
bot/escaner_reversion.py
========================
La MÁQUINA armada: escanea todos los pares con el borde de reversión (bot/senal_reversion)
y entrega las señales operables ordenadas por probabilidad, más la tarjeta lista para
mostrar en Telegram.

Es la pieza que une el borde medido en el historial con el flujo del bot: recibe las
velas de 1m recientes de cada par (del historial + lo que llega en vivo) y decide dónde
hay una reversión con ventaja. No conecta a red: recibe velas, devuelve señales.

Test: bot/test_escaner_reversion.py.
"""
from bot.senal_reversion import senal, BREAKEVEN


def escanear(velas_por_par, expiry_min=3, tabla=None):
    """
    velas_por_par: dict {par: lista_de_cierres_M1_cronologicos}.
    tabla        : tabla de reversión por par (opcional); ver senal_reversion.
    Devuelve la lista de señales OPERABLES, de mayor a menor probabilidad histórica.
    """
    operables = []
    for par, closes in velas_por_par.items():
        s = senal(closes, par, expiry_min, tabla)
        if s.get("operar"):
            operables.append(s)
    operables.sort(key=lambda s: s.get("probabilidad", 0.0), reverse=True)
    return operables


def _flecha(direccion):
    return "baje" if direccion == "PUT" else "suba"


def tarjeta(s):
    """Arma el texto de la tarjeta de señal para Telegram (educativa, sin promesas)."""
    if not s.get("operar"):
        return (f"FUZION FX · {s.get('par','')}\n"
                f"Sin señal: {s.get('motivo','')}")
    lineas = [
        "FUZION FX · SEÑAL DE REVERSIÓN",
        f"Par: {s['par']}",
        f"Dirección: {s['direccion']}  (se espera que {_flecha(s['direccion'])})",
        f"Pico detectado: {s['pips']:+.1f} pips",
        f"Probabilidad histórica: {s['probabilidad']:.1f}%  "
        f"(fuera de muestra, 23 años)",
        f"Vencimiento sugerido: {s['expiry_min']} min",
        f"Ventaja esperada: {s['pnl_esperado']:+.2f}% por operación (payout 92%)",
        f"Break-even: {BREAKEVEN:.1f}%  ·  la probabilidad la supera",
        "Nota: señal educativa. El acierto es estadístico, no garantizado; "
        "opera en demo y con gestión de riesgo.",
    ]
    return "\n".join(lineas)


def resumen(operables):
    """Línea corta del escaneo: cuántas señales y la mejor."""
    if not operables:
        return "Escaneo: sin reversiones con ventaja ahora mismo."
    mejor = operables[0]
    return (f"Escaneo: {len(operables)} señal(es). Mejor: {mejor['par']} "
            f"{mejor['direccion']} {mejor['probabilidad']:.1f}%.")


if __name__ == "__main__":
    ejemplo = {
        "EURUSD": [1.1000, 1.1010],       # +10 pips -> PUT, prob alta
        "GBPUSD": [1.2500, 1.2506],       # +6 pips -> PUT
        "USDJPY": [150.00, 149.95],       # -5 pips -> CALL
        "AUDUSD": [0.6500, 0.65012],      # 1.2 pips -> no opera
    }
    señales = escanear(ejemplo)
    print(resumen(señales), "\n")
    for s in señales:
        print(tarjeta(s), "\n" + "-" * 40)
