"""
bot/sistema_signal.py
=====================
Formatea el veredicto del SISTEMA DEL USUARIO (sinfonía + filtros) en una señal
legible, como saldría en Telegram. Reutiliza veredicto_final (no recalcula).

Este es el puente para conectar el motor: cuando el bot use este formato, las
señales de Telegram saldrán con el sistema del trader (10 indicadores, 12 tiempos,
alineación ponderada, ley EMA200-1H, filtros).

SRP: solo da formato. Sin red. Testeable con asserts.
"""

from bot.filtros import veredicto_final
from bot.scoring_strategy import CALL, PUT

_TF_TXT = {5: "5s", 10: "10s", 15: "15s", 30: "30s", 60: "1m", 120: "2m",
           180: "3m", 300: "5m", 600: "10m", 900: "15m", 1800: "30m", 3600: "1H"}
_FLECHA = {CALL: "⬆️", PUT: "⬇️", "HOLD": "▫️"}


def _tf_txt(tf):
    return _TF_TXT.get(tf, f"{tf}s")


def formatear_senal(res, titulo, asset, tf_operar, extras=""):
    """
    `res`: salida de veredicto_final. Devuelve el texto de la señal.
    `titulo`: nombre del bot (ej. 'Fuzion POption OTC'). `tf_operar`: expiración.
    `extras`: bloque de LECTURA opcional (hora de entrada, VWAP, techo/piso,
    patrones, historial) que se inserta antes del aviso. Vacío = tarjeta simple.
    """
    dir_1h = res.get("direccion_1h", "HOLD")
    ver = res.get("veredicto", "NO OPERAR")
    flecha = {CALL: "⬆️ CALL", PUT: "⬇️ PUT"}.get(dir_1h, "⏸️ sin dirección")
    icono = "✅" if ver == "OPERAR" else "🚫"

    # Panel de las 12 temporalidades (dirección de cada una).
    filas = []
    for tf in sorted(res.get("dir_por_tf", {})):
        d = res["dir_por_tf"][tf]
        marca = "•" if d == dir_1h and dir_1h in (CALL, PUT) else " "
        filas.append(f"{marca}`{_tf_txt(tf):>3}` {_FLECHA.get(d, '▫️')}")
    panel = "  ".join(filas)

    # Filtros.
    filt = res.get("filtros", {})
    if filt.get("fallos"):
        filtros_txt = "\n🛡️ *Filtros:* " + "; ".join(filt["fallos"])
    elif filt.get("avisos"):
        filtros_txt = "\n🛡️ _" + "; ".join(filt["avisos"]) + "_"
    else:
        filtros_txt = "\n🛡️ Filtros: OK (payout/sesión/noticias)"

    return (
        f"🤖 *{titulo}*  ·  📈 *{asset}*  ·  ⏱️ *{tf_operar}*\n"
        f"\n{icono} *{ver}*   Dirección (EMA200 1H): {flecha}\n"
        f"🎼 Alineación: *{res.get('alineados', 0)}/{res.get('total_tf', 0)}* "
        f"tiempos · peso *{res.get('peso_favor', 0)}%*\n"
        f"🧭 {res.get('motivo', '')}"
        f"{filtros_txt}\n"
        f"\n🔎 *12 tiempos:*\n{panel}\n"
        f"{chr(10) + extras + chr(10) if extras else ''}"
        f"\n⚠️ _Señal educativa, demo, solo lectura. El acierto real lo mide el "
        f"registro; ningún sistema gana siempre._"
    )


def lectura_extra(seg, old):
    """
    Bloque de LECTURA extra con el mismo formato que la tarjeta clásica:
    hora de entrada (lo más pedido para operar), VWAP, techo/piso, patrones e
    historial. `seg`: segundos hasta que ABRE la próxima vela (para la hora de
    entrada). `old`: dict del análisis clásico (vwap/levels/patrones/m1_count).
    Devuelve el bloque ya formateado (o "" si no hay nada que mostrar).
    """
    from datetime import datetime, timedelta
    partes = []
    # HORA DE ENTRADA: el momento EXACTO en que abre la próxima vela del tiempo de
    # operación. Es lo que faltaba para poder operar (saber cuándo entrar).
    if seg is not None:
        hora = (datetime.now() + timedelta(seconds=int(seg))).strftime("%H:%M:%S")
        if int(seg) <= 5:
            partes.append(f"⏱️ *¡ENTRA YA!* (nueva vela ~{hora})")
        else:
            partes.append(f"⏱️ *Entra a las {hora}* "
                          f"_(al abrir la vela, en {int(seg)}s)_")
    old = old or {}
    pats = old.get("patrones")
    if pats:
        partes.append(f"🕯️ *Patrones:* {', '.join(pats)}")
    vw = old.get("vwap")
    if vw and vw.get("vwap") is not None:
        lado = {"CALL": "por ENCIMA (sesgo alcista)",
                "PUT": "por DEBAJO (sesgo bajista)",
                "HOLD": "pegado al VWAP (neutral)"}.get(vw.get("side"), "")
        partes.append(f"📏 *VWAP:* precio {lado} _({vw['dist_pct']:+.2f}%)_")
    lv = old.get("levels")
    if lv and (lv.get("resistencias") or lv.get("soportes")):
        techo = f"{lv['resistencias'][0]:.5f}" if lv.get("resistencias") else "—"
        piso = f"{lv['soportes'][0]:.5f}" if lv.get("soportes") else "—"
        partes.append(f"🧱 *Techo:* {techo}  ·  *Piso:* {piso}")
    m1 = old.get("m1_count")
    if m1 is not None:
        partes.append(f"📚 Historial: {m1} velas M1 acumuladas")
    return "\n".join(partes)


def senal(frames, sistema, titulo, asset, tf_operar, payout=None,
          hay_noticia=False, hora_est=None, spread=None, extras=""):
    """Atajo: calcula el veredicto final y lo formatea de una."""
    res = veredicto_final(frames, sistema, payout=payout, hay_noticia=hay_noticia,
                          hora_est=hora_est, spread=spread)
    return formatear_senal(res, titulo, asset, tf_operar, extras=extras), res


def _clave_repo(tf):
    """Clave en la BD: 60 -> 'M1'; el resto -> 'tf<segundos>'."""
    return "M1" if tf == 60 else f"tf{tf}"


def frames_desde_repo(repo, sistema, asset, minimo_velas=6):
    """
    Arma las 12 temporalidades del sistema desde el historial guardado.
    {tf: DataFrame}. Un tiempo sin velas suficientes NO se incluye (el veredicto
    lo trata como sin dirección, honesto: no inventa). Para EMA200 hacen falta
    ~200 velas de ese tiempo; si no las hay, ese tiempo no cuenta.
    """
    from bot.data_quality import frames_limpios
    frames = {}
    for tf in sistema.TIMEFRAMES:                # canónico (OTC o real)
        df = repo.get_recent(asset, _clave_repo(tf), 400)
        if df is not None and len(df) >= minimo_velas:
            frames[tf] = df
    # BARRERA DE SEGURIDAD: descarta series basura (planas, NaN, corruptas, con
    # saltos imposibles) para no producir señales absurdas. Solo pasan los sanos.
    limpios, _descartados = frames_limpios(frames)
    return limpios


def senal_desde_repo(repo, sistema, titulo, asset, asset_display, tf_operar,
                     payout=None, hay_noticia=False, hora_est=None, spread=None,
                     extras=""):
    """
    Construye la señal del sistema para un activo leyendo su historial del repo.
    Devuelve (texto, resultado). Si faltan temporalidades (poca historia), el
    veredicto será NO OPERAR con su motivo — es correcto, no se fuerza.
    `extras`: bloque de lectura (hora de entrada, VWAP...) ya formateado.
    """
    frames = frames_desde_repo(repo, sistema, asset)
    return senal(frames, sistema, titulo, asset_display, tf_operar,
                 payout=payout, hay_noticia=hay_noticia, hora_est=hora_est,
                 spread=spread, extras=extras)


def _demo():
    """Ejemplo con datos alcistas alineados (para VER la señal)."""
    import numpy as np
    import pandas as pd
    from bot import otc_system

    tfs = [5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600]

    def df(n=260):
        c = pd.Series([100 + i * 0.2 + np.sin(i / 6) * 0.2 for i in range(n)],
                      dtype=float)
        return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]),
                             "high": c + 0.15, "low": c - 0.15, "close": c})

    frames = {tf: df() for tf in tfs}
    texto, _ = senal(frames, otc_system, "Fuzion POption OTC", "EUR/USD OTC",
                     "M5", payout=82)
    print(texto)


if __name__ == "__main__":
    _demo()
