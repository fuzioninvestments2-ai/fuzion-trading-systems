"""
scripts/por_que_no_hay_senales.py (fuzion_fx)
=============================================
DIAGNOSTICO: dice, en lenguaje claro, POR QUE el bot no esta enviando senales.
Recorre TODAS las compuertas que puede frenar una emision y reporta cual esta
bloqueando, con numeros reales de la base del colector y de la memoria de cada bot.

No toca nada (solo lee). No usa red. Pensado para correr con el sistema prendido.

    python fuzion_fx/scripts/por_que_no_hay_senales.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

DB = os.path.join(_RAIZ, "data", "db", "po_candles.db")
_TF = {60: "M1", 120: "M2", 180: "M3", 300: "M5"}


def _cfg():
    """Carga config (market, payout, pares). Defensivo: si falla, defaults."""
    try:
        from core.config import load_config
        c = load_config()
        return c
    except Exception as exc:
        print(f"[!] No se pudo leer config/bots.yaml: {exc}")
        return {}


def _seccion(titulo: str) -> None:
    print("\n" + "=" * 60)
    print(titulo)
    print("=" * 60)


def _edad(seg: float) -> str:
    seg = int(seg)
    if seg < 90:
        return f"{seg}s"
    if seg < 5400:
        return f"{seg // 60}min"
    return f"{seg // 3600}h"


def main() -> None:
    ahora = time.time()
    cfg = _cfg()
    market = str(cfg.get("market", "otc")).lower()
    pf = cfg.get("payout", {}) or {}
    pmin = float(pf.get("min_pct", 72))
    pmax = float(pf.get("max_pct", 92))
    require = bool(pf.get("require", True))
    pares = []
    try:
        pares = cfg.get("bots", {}).get("f1_m1", {}).get("pairs", []) or []
    except Exception:
        pares = []

    print("DIAGNOSTICO FUZION FX — por que no hay senales")
    print(f"Mercado configurado: {market.upper()}   "
          f"Filtro de pago: {pmin:.0f}%-{pmax:.0f}% (require={require})")

    # -------------------------------------------------- 1) colector / base
    _seccion("1) COLECTOR Y BASE DE DATOS")
    if not os.path.exists(DB):
        print("  [X] No existe po_candles.db. El colector NO arranco o no escribio.")
        print("      -> Arranca el sistema (FUZION.vbs) y espera 1-2 min.")
        return
    edad_db = ahora - os.path.getmtime(DB)
    estado_col = "OK" if edad_db < 180 else "MUDO (revisar conexion/horario)"
    print(f"  Ultima escritura de la base: hace {_edad(edad_db)}  -> {estado_col}")
    conn = sqlite3.connect(DB, timeout=5.0)

    # -------------------------------------------------- 2) pausa global
    _seccion("2) PAUSA GLOBAL (boton del panel)")
    pausado = False
    try:
        from core import control
        pausado = control.esta_pausado()
    except Exception:
        pass
    print(f"  Pausado: {'SI -> por eso no emite. Reanuda en el panel.' if pausado else 'no'}")

    # -------------------------------------------------- 3) velas reales
    _seccion("3) VELAS REALES (candles_real) — insumo del analisis")
    try:
        filas = conn.execute(
            """SELECT pair, tf, COUNT(*), MAX(ts) FROM candles_real
               GROUP BY pair, tf""").fetchall()
    except sqlite3.Error:
        filas = []
    reales = {}
    for pair, tf, n, ts_max in filas:
        reales.setdefault(pair, {})[tf] = (n, ts_max)
    if not filas:
        print("  [X] NO hay velas reales todavia.")
        print("      En mercado REAL esto pasa si el mercado FX esta CERRADO")
        print("      (noche/fin de semana) o el colector recien arranco.")
    else:
        listos = 0
        for pair in pares:
            tfs = reales.get(pair)
            if not tfs:
                continue
            partes = []
            for tf in (60, 120, 180, 300):
                if tf in tfs:
                    n, ts_max = tfs[tf]
                    partes.append(f"{_TF[tf]}:{n}")
            if any(tf in tfs and tfs[tf][0] >= 2 for tf in (60, 120, 180, 300)):
                listos += 1
        print(f"  Pares con velas reales suficientes (>=2 en algun TF): {listos}/{len(pares)}")
        if listos == 0:
            print("  [X] Ningun par tiene >=2 velas reales -> el motor no puede analizar.")

    # -------------------------------------------------- 4) pagos (payout)
    _seccion("4) PAGOS (payout) — el filtro que mas silencia")
    try:
        pagos = conn.execute("SELECT pair, payout FROM payouts").fetchall()
    except sqlite3.Error:
        pagos = []
    if not pagos:
        print("  [X] NO hay pagos cargados. Con require=True eso BLOQUEA TODO.")
        print("      PO manda los pagos en updateAssets; si no llegaron, el colector")
        print("      aun no los recibio (espera 1-2 min) o hay que revisar conexion.")
    else:
        en_banda = [(p, v) for (p, v) in pagos if pmin <= v <= pmax]
        fuera = [(p, v) for (p, v) in pagos if not (pmin <= v <= pmax)]
        print(f"  Pares con pago cargado: {len(pagos)}")
        print(f"  DENTRO de la banda {pmin:.0f}-{pmax:.0f}%: {len(en_banda)}")
        if en_banda:
            muestra = ", ".join(f"{p} {v:.0f}%" for p, v in sorted(
                en_banda, key=lambda x: -x[1])[:12])
            print(f"    -> {muestra}")
        else:
            top = ", ".join(f"{p} {v:.0f}%" for p, v in sorted(
                fuera, key=lambda x: -x[1])[:8])
            print("  [X] NINGUN par en la banda. Por eso no emite.")
            print(f"      Mejores pagos disponibles ahora: {top}")
            print(f"      En mercado REAL los pagos suelen ser < {pmin:.0f}%. Opciones:")
            print(f"        a) esperar horario de mayor pago, o")
            print(f"        b) bajar payout.min_pct en config/bots.yaml.")

    # -------------------------------------------------- 5) memoria de los bots
    _seccion("5) MEMORIA DE LOS BOTS (emitidas / pendientes / resueltas)")
    for bot_id in ("f1_m1", "f2_m2", "f3_m3", "f4_m5"):
        db_bot = os.path.join(_RAIZ, "data", "db", f"{bot_id.split('_')[0]}_memory.db")
        if not os.path.exists(db_bot):
            print(f"  {bot_id}: sin base aun ({os.path.basename(db_bot)})")
            continue
        try:
            c = sqlite3.connect(db_bot, timeout=5.0)
            tot = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            pend = c.execute(
                "SELECT COUNT(*) FROM signals WHERE resolved=0").fetchone()[0]
            res = c.execute(
                "SELECT COUNT(*) FROM signals WHERE resolved=1").fetchone()[0]
            ult = c.execute("SELECT MAX(ts) FROM signals").fetchone()[0]
            c.close()
            ult_txt = f"hace {_edad(ahora - ult)}" if ult else "nunca"
            print(f"  {bot_id}: emitidas={tot}  pendientes={pend}  "
                  f"resueltas={res}  ultima={ult_txt}")
        except sqlite3.Error as exc:
            print(f"  {bot_id}: error leyendo memoria ({exc})")

    conn.close()

    # -------------------------------------------------- VEREDICTO
    _seccion("VEREDICTO")
    if pausado:
        print("  El sistema esta EN PAUSA. Reanuda desde el panel.")
    elif not filas:
        print("  Falta VELAS REALES. En mercado REAL, confirma que el mercado FX")
        print("  este abierto; deja el colector 2-3 min y volve a correr esto.")
    elif not pagos:
        print("  Faltan los PAGOS (updateAssets no llego aun). Espera 1-2 min con")
        print("  el colector prendido; si sigue vacio, revisa la conexion a PO.")
    elif pagos and not [1 for (p, v) in pagos if pmin <= v <= pmax]:
        print("  El FILTRO DE PAGO deja fuera a TODOS los pares (ninguno en la")
        print(f"  banda {pmin:.0f}-{pmax:.0f}%). En real es lo mas comun. Baja")
        print("  payout.min_pct o espera un horario con mejor pago.")
    else:
        print("  Datos y pagos OK. Si aun no emite, es que el MOTOR no encontro")
        print("  una senal con 3 de 4 confirmaciones, o el pre-filtro la descarto")
        print("  (la direccion cambio en 10s). Es NORMAL: solo emite en setups")
        print("  claros. Deja correr; revisa logs/f*_log para el detalle por par.")


if __name__ == "__main__":
    main()
