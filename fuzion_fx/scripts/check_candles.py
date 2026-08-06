"""
scripts/check_candles.py (fuzion_fx)
====================================
Muestra cuantas velas junto el colector en po_candles.db, por par y timeframe.
Sirve para verificar que el colector esta recibiendo datos de Pocket Option.

    python fuzion_fx/scripts/check_candles.py
"""

from __future__ import annotations

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # fuzion_fx/
DB = os.path.join(ROOT, "data", "db", "po_candles.db")

_TF_LABEL = {60: "M1", 120: "M2", 180: "M3", 300: "M5"}


def main() -> None:
    if not os.path.exists(DB):
        print(f"Todavia no existe {DB}.")
        print("El colector no arranco o aun no escribio nada. Arrancalo con:")
        print("   python collector\\po_collector.py")
        return

    conn = sqlite3.connect(DB)
    total = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    print(f"Total de velas guardadas: {total}\n")
    if total == 0:
        print("Sin velas aun. Deja el colector corriendo un rato (el mercado FX "
              "debe estar abierto) y volve a chequear.")
        return

    print(f"{'PAR':<10} {'TF':<4} {'VELAS':>6}  ULTIMO CIERRE")
    rows = conn.execute(
        """SELECT pair, tf, COUNT(*), MAX(ts) FROM candles
           GROUP BY pair, tf ORDER BY pair, tf""").fetchall()
    for pair, tf, n, ts_max in rows:
        ult = conn.execute(
            "SELECT close FROM candles WHERE pair=? AND tf=? ORDER BY ts DESC LIMIT 1",
            (pair, tf)).fetchone()
        label = _TF_LABEL.get(tf, str(tf))
        print(f"{pair:<10} {label:<4} {n:>6}  {ult[0] if ult else '-'}")
    conn.close()


if __name__ == "__main__":
    main()
