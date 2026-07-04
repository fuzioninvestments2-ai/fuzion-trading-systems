"""
bot/auditoria.py
================
AUDITOR DE COMPLETITUD (filtro multi-pasada). Objetivo del usuario: "no dejar
archivos atrás, no saltar páginas... filtrada 5 veces o más que no se nos quede
nada pendiente". Este módulo NO descarga: AUDITA lo ya bajado (datasets/) y dice,
por cada activo×temporalidad, qué está COMPLETO y qué queda PENDIENTE de
re-escanear. Así el escáner puede volver SOLO a lo que falta (sin repetir todo).

Las 5 pasadas (una serie sana pasa las cinco):
  1) EXISTE      -> hay archivo para ese activo×tf (si falta, pendiente).
  2) NO BASURA   -> calidad_serie() lo aprueba (no plano/NaN/precio<=0/saltos).
  3) SIN HUECOS  -> los timestamps son contiguos al `period` (sin agujeros
                    grandes); se tolera un % de huecos (fines de semana/cierres).
  4) SIN DUPLICADOS -> no hay timestamps repetidos (doble inserción).
  5) COMPLETO    -> nº de velas >= umbral esperado para ese tf.

SRP: solo juzga completitud sobre disco. Sin red. Testeable con asserts.
"""

import gzip
import os

from bot.data_quality import calidad_serie, MIN_VELAS

# Umbral de velas para considerar "completo" cada tramo de la escalera. Los
# tiempos cortos (5s..1m) PO los sirve por miles; los largos (4h/1d) por pocos
# cientos como mucho. Umbral por defecto, ajustable por tf abajo.
COMPLETO_POR_DEFECTO = 500
UMBRAL_COMPLETO = {
    "M1": 3000, "tf5": 2000, "tf10": 2000, "tf15": 2000, "tf30": 2000,
    "tf120": 1500, "tf180": 1500, "tf300": 1500, "tf600": 1000, "tf900": 1000,
    "tf1800": 800, "tf3600": 500, "tf14400": 150, "tf86400": 60,
}

# Tolerancia de huecos: fracción de intervalos que puede faltar sin marcar
# "con huecos" (el mercado real cierra fines de semana; PO OTC casi no).
HUECOS_TOLERADOS = 0.20


def _segundos_de_tf(tf):
    """'M1' -> 60; 'tf300' -> 300. None si no se reconoce."""
    if tf == "M1":
        return 60
    if tf.startswith("tf"):
        try:
            return int(tf[2:])
        except ValueError:
            return None
    return None


def _leer_timestamps(ruta):
    """Lee los timestamps (ms, ordenados) de un .csv.gz. [] si no se puede."""
    ts = []
    try:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            cabecera = True
            for linea in f:
                if cabecera:                      # saltar fila de columnas
                    cabecera = False
                    continue
                col = linea.split(",", 1)[0].strip()
                if col:
                    ts.append(int(float(col)))
    except Exception:
        return []
    ts.sort()
    return ts


def _df_desde_csv_gz(ruta):
    """Carga un .csv.gz a DataFrame OHLC (para calidad_serie). None si falla."""
    try:
        import pandas as pd
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return pd.read_csv(f)
    except Exception:
        return None


def _huecos(timestamps, period_s):
    """
    Fracción de intervalos FALTANTES en la serie. 0.0 = perfectamente contigua.
    Cuenta cuántos pasos de `period_s` deberían existir entre el primer y último
    timestamp y cuántos faltan. Tolera duplicados (se ignoran en el conteo).
    """
    if len(timestamps) < 2 or period_s <= 0:
        return 0.0
    paso_ms = period_s * 1000
    esperados = (timestamps[-1] - timestamps[0]) // paso_ms + 1
    reales = len(set(timestamps))
    if esperados <= 0:
        return 0.0
    faltan = max(0, esperados - reales)
    return faltan / esperados


def auditar_serie(ruta, tf):
    """
    Aplica las 5 pasadas a UN archivo. Devuelve dict con el veredicto y el detalle
    de cada pasada. `completo` True solo si pasa las CINCO.
    """
    nombre = os.path.basename(ruta)
    period_s = _segundos_de_tf(tf) or 60
    ts = _leer_timestamps(ruta)
    n = len(ts)

    # 2) NO BASURA (reusa la barrera de calidad).
    df = _df_desde_csv_gz(ruta)
    sana, motivo_calidad = calidad_serie(df, MIN_VELAS)

    # 3) SIN HUECOS.
    frac_huecos = _huecos(ts, period_s)
    sin_huecos = frac_huecos <= HUECOS_TOLERADOS

    # 4) SIN DUPLICADOS.
    duplicados = n - len(set(ts))
    sin_duplicados = duplicados == 0

    # 5) COMPLETO (nº de velas).
    umbral = UMBRAL_COMPLETO.get(tf, COMPLETO_POR_DEFECTO)
    suficientes = n >= umbral

    completo = bool(sana and sin_huecos and sin_duplicados and suficientes)
    motivos = []
    if not sana:
        motivos.append(f"basura ({motivo_calidad})")
    if not sin_huecos:
        motivos.append(f"huecos {frac_huecos*100:.0f}%")
    if not sin_duplicados:
        motivos.append(f"{duplicados} duplicados")
    if not suficientes:
        motivos.append(f"pocas velas ({n}<{umbral})")
    return {
        "archivo": nombre, "tf": tf, "velas": n, "completo": completo,
        "sana": sana, "sin_huecos": sin_huecos, "sin_duplicados": sin_duplicados,
        "suficientes": suficientes, "frac_huecos": frac_huecos,
        "duplicados": duplicados, "motivos": motivos,
    }


def auditar_carpeta(carpeta):
    """
    Audita TODOS los .csv.gz de una carpeta. Devuelve (completos, pendientes)
    donde cada elemento es el dict de auditar_serie(). `pendientes` = lo que hay
    que re-escanear (no pasa las 5 pasadas).
    """
    completos, pendientes = [], []
    if not os.path.isdir(carpeta):
        return completos, pendientes
    for fn in sorted(os.listdir(carpeta)):
        if not fn.endswith(".csv.gz") or "__" not in fn:
            continue
        base = fn[:-len(".csv.gz")]
        _, tf = base.rsplit("__", 1)
        res = auditar_serie(os.path.join(carpeta, fn), tf)
        (completos if res["completo"] else pendientes).append(res)
    return completos, pendientes


def faltantes_por_activo(carpeta, activos, escalera):
    """
    Detecta activo×tf que NO tienen archivo (pasada 1: EXISTE). Devuelve
    {activo: [tf_que_faltan]}. `escalera` en segundos (60->'M1', N->'tf<N>').
    """
    def _clave(p):
        return "M1" if p == 60 else f"tf{p}"

    presentes = set()
    if os.path.isdir(carpeta):
        for fn in os.listdir(carpeta):
            if fn.endswith(".csv.gz") and "__" in fn:
                base = fn[:-len(".csv.gz")]
                safe, tf = base.rsplit("__", 1)
                presentes.add((safe.replace("-", "/"), tf))
    faltan = {}
    for a in activos:
        for p in escalera:
            if (a, _clave(p)) not in presentes:
                faltan.setdefault(a, []).append(_clave(p))
    return faltan


def _main():
    """
    CLI: audita la completitud de un bot y lista lo PENDIENTE de re-escanear.
      python -m bot.auditoria           # OTC
      python -m bot.auditoria real       # REAL
    """
    import sys
    from bot.profiles import get_profile

    perfil = "REAL" if any(a.lower() == "real" for a in sys.argv[1:]) else "OTC"
    p = get_profile(perfil)
    completos, pendientes = auditar_carpeta(p.datasets_dir)
    faltan = faltantes_por_activo(p.datasets_dir, p.activos, p.ladder)

    total = len(completos) + len(pendientes)
    print(f"[{p.titulo}] auditoría de {p.datasets_dir}")
    print(f"  archivos: {total} · completos: {len(completos)} · "
          f"pendientes: {len(pendientes)}")
    if pendientes:
        print("  PENDIENTES (re-escanear):")
        for r in pendientes[:40]:
            print(f"   · {r['archivo']}: {', '.join(r['motivos'])}")
        if len(pendientes) > 40:
            print(f"   ... y {len(pendientes) - 40} más")
    if faltan:
        n_faltan = sum(len(v) for v in faltan.values())
        print(f"  SIN ARCHIVO ({n_faltan} activo×tf sin bajar):")
        for a, tfs in list(faltan.items())[:20]:
            print(f"   · {a}: faltan {', '.join(tfs)}")
        if len(faltan) > 20:
            print(f"   ... y {len(faltan) - 20} activos más con faltantes")
    if not pendientes and not faltan:
        print("  TODO COMPLETO. Nada pendiente.")


if __name__ == "__main__":
    _main()
