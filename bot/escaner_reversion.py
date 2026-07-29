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

# Segundos que tiene el trader para poner la operación (la vela nueva dura 60s; se
# recomienda entrar en los primeros ~45 para no llegar tarde a la reversión).
VENTANA_ENTRADA_SEG = 45


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


def tarjeta(s):
    """Tarjeta de señal para Telegram: corta y de un vistazo (par, dirección, tiempo)."""
    if not s.get("operar"):
        return f"FUZION FX · {s.get('par','')}\nSin señal: {s.get('motivo','')}"
    if s["direccion"] == "PUT":
        color, accion = "🔴", "BAJA  (poner ABAJO / PUT)"
    else:
        color, accion = "🟢", "SUBE  (poner ARRIBA / CALL)"
    pago = s.get("payout")
    linea_pago = f"💰 Pago del activo: {pago:.0f}%\n" if pago else ""
    # Si el robot puso la hora, se muestra la hora EXACTA de entrada y de vencimiento.
    if s.get("hora_entrada"):
        tiempo = (f"⏰ ENTRA en la vela de las {s['hora_entrada']}  "
                  f"(ya, tienes ~{VENTANA_ENTRADA_SEG} seg)\n"
                  f"🏁 Vence a las {s['hora_vence']}  "
                  f"({s['expiry_min']} min · M{s['expiry_min']})\n")
    else:
        tiempo = (f"⏳ PON LA OPERACIÓN YA — tienes ~{VENTANA_ENTRADA_SEG} seg\n"
                  f"🕒 Vencimiento: {s['expiry_min']} min  (elige M{s['expiry_min']})\n")
    return (
        f"{color} {s['par']}  ·  {accion}\n"
        f"{tiempo}"
        f"{linea_pago}"
        f"🎯 Acierto histórico: {s['probabilidad']:.0f}%   (23 años reales)\n"
        f"📊 Pico {s['pips']:+.1f} pips · ventaja +{s['pnl_esperado']:.1f}%\n"
        f"⚠ Demo · el acierto no está garantizado"
    )


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
