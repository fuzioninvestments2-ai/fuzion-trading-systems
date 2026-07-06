"""
bot/simular_reglas.py
=====================
SIMULACIÓN de las reglas estrictas (validate_signal) sobre las ÚLTIMAS N señales
que el bot ya generó y RESOLVIÓ (win/loss). Muestra un reporte:
  - win-rate ANTES (todas las señales).
  - cuántas se hubieran FILTRADO (rechazado) con las reglas nuevas.
  - win-rate ESTIMADO de las que SÍ hubieran pasado.
  - motivos de rechazo más comunes.

Las señales viejas solo guardaban votos+resultado, así que para ellas se
reconstruye lo posible (alineación desde los votos). Las señales NUEVAS guardan
toda la metadata (columna 'meta') -> simulación COMPLETA. El reporte dice cuántas
usaron metadata completa.

Uso:
    python bot/simular_reglas.py [ruta_history.db] [N=100]
"""
import json
import os
import sqlite3
import sys
from collections import Counter

from bot.validacion_senal import validate_signal


def _alineacion_desde_votos(votes_json, direction):
    """% de indicadores (votos) que coinciden con la dirección de la señal."""
    if not votes_json:
        return None
    try:
        votes = json.loads(votes_json)
    except Exception:
        return None
    if not votes:
        return None
    a = sum(1 for v in votes.values() if v == direction)
    return a / len(votes) * 100.0


def _categoria(motivo):
    m = motivo.lower()
    if "faltan" in m:
        return "Faltan tiempos por datos"
    if "alineación" in m:
        return "Alineación < 80%"
    if "win-rate" in m:
        return "Win-rate < 60%"
    if "ruido" in m:
        return "Indicador en zona de ruido (45-55%)"
    if "umbral" in m:
        return "Umbral aprendido < 25%"
    if "pegado" in m:
        return "Precio pegado a soporte/resistencia"
    if "confirmación" in m:
        return "Confirmación por timeframe baja"
    if "< 60%" in m:
        return "Indicador débil (<60%)"
    return motivo[:40]


def simular(db_path, n=100):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT direction, result, votes, meta FROM signals "
            "WHERE result IN ('win','loss') ORDER BY id DESC LIMIT ?",
            (n,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"No se pudo leer la base ({e}).")
        return
    if not rows:
        print("No hay señales RESUELTAS (win/loss) todavía en esta base.")
        print("Deja el bot operando un rato para que acumule señales y vuelve.")
        return

    total = len(rows)
    wins_all = sum(1 for r in rows if r[1] == "win")
    pasan, rechazos, con_meta = [], Counter(), 0
    for direction, result, votes_json, meta_json in rows:
        datos = None
        if meta_json:
            try:
                datos = json.loads(meta_json)
                con_meta += 1
            except Exception:
                datos = None
        if datos is None:
            # Reconstrucción PARCIAL (solo alineación desde votos).
            ali = _alineacion_desde_votos(votes_json, direction)
            datos = {"alineacion_pct": ali if ali is not None else 0.0,
                     "tiempos_presentes": 12, "tiempos_config": 12,
                     "senales_medidas": 0}
        v = validate_signal(datos)
        if v["operar"]:
            pasan.append(result)
        else:
            rechazos[_categoria(v["motivo"])] += 1

    wr_all = wins_all / total * 100.0
    n_pasan = len(pasan)
    wins_pasan = sum(1 for r in pasan if r == "win")
    wr_pasan = (wins_pasan / n_pasan * 100.0) if n_pasan else 0.0

    print("=" * 60)
    print(f"SIMULACIÓN DE REGLAS ESTRICTAS — últimas {total} señales resueltas")
    print("=" * 60)
    print(f"Metadata completa: {con_meta}/{total} señales "
          f"({total - con_meta} con reconstrucción parcial por votos)")
    print()
    print(f"ANTES  (sin reglas):  {total} señales · win-rate {wr_all:.0f}% "
          f"({wins_all} wins / {total - wins_all} losses)")
    print(f"FILTRADAS (rechazadas por las reglas): {total - n_pasan}")
    print(f"PASAN las reglas:     {n_pasan} señales · win-rate ESTIMADO "
          f"{wr_pasan:.0f}% ({wins_pasan} wins / {n_pasan - wins_pasan} losses)")
    print()
    if rechazos:
        print("Motivos de rechazo más comunes:")
        for motivo, c in rechazos.most_common(8):
            print(f"   {c:3}x  {motivo}")
    print("=" * 60)


def _localizar_db(arg):
    if arg and os.path.exists(arg):
        return arg
    for cand in ("history.db", os.path.join("fuzion-otc", "history.db"),
                 os.path.join("fuzion-real", "history_real.db")):
        if os.path.exists(cand):
            return cand
    return None


if __name__ == "__main__":
    db = _localizar_db(sys.argv[1] if len(sys.argv) > 1 else None)
    if not db:
        print("No encontré la base. Uso: python bot/simular_reglas.py <history.db> [N]")
        sys.exit(1)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    print(f"Base: {db}\n")
    simular(db, n)
