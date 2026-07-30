"""
bot/mantenimiento.py
====================
Limpieza y DIAGNÓSTICO del historial en vivo (history_real.db). Borra lo que "no
procede" y alinea los datos a lo que los bots realmente usan:

  1) Velas MAL ALINEADAS: su timestamp no cae en el borde de su temporalidad (dato
     roto/mal metido) -> se borran.
  2) Tiempos NO USADOS: los bots operan 1/2/3/5m (M1/tf120/tf180/tf300). Tiempos
     largos guardados antes (tf600/900/1800/3600) no los analiza nadie -> se borran.
  3) Activos OTC en la base REAL (sintéticos) -> se borran.
  Al final compacta la base (VACUUM).

También imprime un DIAGNÓSTICO: cuántas velas hay por par/tiempo y si ese par/tiempo
tiene borde en reversion_tabla.json (por qué un bot podría estar callado).

Sin red. Test: bot/test_mantenimiento.py.
"""
import os

# Temporalidades que SÍ usan los bots (segundos por clave de la tabla candles).
TIEMPOS_USADOS = {"M1": 60, "tf120": 120, "tf180": 180, "tf300": 300}


def _seg_de(timeframe):
    """Segundos de una clave de tiempo ('M1'->60, 'tf300'->300). None si no se reconoce."""
    if timeframe == "M1":
        return 60
    if timeframe.startswith("tf"):
        try:
            return int(timeframe[2:])
        except ValueError:
            return None
    return None


def limpiar(repo, tiempos_usados=None):
    """Borra del repo lo que no procede y compacta. Devuelve el conteo de lo borrado:
    {desalineadas, no_usados, otc}."""
    usados = tiempos_usados or TIEMPOS_USADOS
    conn = repo.conn
    borrado = {"desalineadas": 0, "no_usados": 0, "otc": 0}
    with repo._lock:
        # Tiempos presentes en la base.
        tiempos = [r[0] for r in conn.execute(
            "SELECT DISTINCT timeframe FROM candles").fetchall()]
        for tf in tiempos:
            if tf not in usados:
                # Tiempo que ningún bot usa -> fuera.
                cur = conn.execute("DELETE FROM candles WHERE timeframe=?", (tf,))
                borrado["no_usados"] += cur.rowcount
                continue
            # Velas mal alineadas a su borde (ts no es múltiplo de seg*1000).
            paso = usados[tf] * 1000
            cur = conn.execute(
                "DELETE FROM candles WHERE timeframe=? AND (ts % ?) != 0", (tf, paso))
            borrado["desalineadas"] += cur.rowcount
        # Activos OTC (sintéticos) que no deberían estar en la base REAL.
        otc = [r[0] for r in conn.execute(
            "SELECT DISTINCT asset FROM candles").fetchall() if "_otc" in str(r[0]).lower()]
        for a in otc:
            cur = conn.execute("DELETE FROM candles WHERE asset=?", (a,))
            borrado["otc"] += cur.rowcount
        conn.commit()
        conn.execute("VACUUM")
    return borrado


def diagnostico(repo, tabla=None):
    """Imprime, por par y tiempo, cuántas velas hay y si tiene borde en la tabla. Ayuda a
    ver por qué un bot está callado (sin borde medido o sin datos)."""
    filas = repo.assets_tracked()
    print("DIAGNÓSTICO DEL HISTORIAL (velas por par/tiempo · borde en la tabla)")
    print("=" * 62)
    exp_de = {"M1": "1", "tf120": "2", "tf180": "3", "tf300": "5"}
    for f in filas:
        a, tf, n = f["asset"], f["timeframe"], f["velas"]
        borde = "-"
        if tabla and a in tabla and isinstance(tabla[a], dict):
            k = exp_de.get(tf)
            if k and tabla[a].get(k):
                mejor = max(wr for _, wr in tabla[a][k])
                borde = f"{mejor:.0f}%"
        print(f"  {a:10} {tf:6} {n:>8} velas   borde:{borde}")
    print("=" * 62)


if __name__ == "__main__":
    import argparse
    from bot.history import HistoryRepository
    from bot.profiles import get_profile
    from bot.senal_reversion import cargar_tabla

    ap = argparse.ArgumentParser(description="Limpieza y diagnóstico del historial real.")
    ap.add_argument("--perfil", default="REAL")
    ap.add_argument("--solo-diagnostico", action="store_true",
                    help="no borra nada, solo muestra el estado")
    a = ap.parse_args()
    prof = get_profile(a.perfil)
    repo = HistoryRepository(prof.db_path)
    tabla = cargar_tabla(os.path.join(prof.datasets_dir, "reversion_tabla.json"))
    if not a.solo_diagnostico:
        b = limpiar(repo)
        print(f"Limpieza: {b['desalineadas']} desalineadas, {b['no_usados']} de tiempos "
              f"no usados, {b['otc']} OTC. Base compactada.")
    diagnostico(repo, tabla)
