"""
bot/backtest_real_v3.py
=======================
BACKTEST REAL v3 — busca DÓNDE vive el acierto y afina la regla para pasar del 50%.

El v2 dejó una pista: todas las señales OPERAR tienen alineación 1.0 (el motor solo
opera con alineación perfecta), así que cortar por "fuerza" no separa nada. Aquí se
corta por ejes que SÍ varían y que sí pueden esconder borde:

  - REGIMEN del mercado (tendencia 'slide' vs rango 'oscillate' vs 'mixto').
  - Nº de TIEMPOS confirmados (3, 4, 5+).
  - ALINEACION FRACTAL: de TODOS los tiempos (no solo los confirmados), cuántos
    coinciden. Es la "confluencia total".
  - SESION horaria (Asia / Europa / EEUU / tarde), por hora UTC de la vela.

Método sin trampa: en TRAIN (hasta el corte) se mide el acierto por cada valor de
esos ejes y se elige la REGLA que gana (régimen + corte de fractal con win-rate de
train > break-even y muestra suficiente). Esa regla FIJA se aplica en TEST (que nunca
se vio) y se reporta su win-rate fuera de muestra. Si el bolsillo de borde existe,
sale aquí; si no, el número lo dice.

Break-even payout 92% = 52.08%. Sin red salvo lectura de .csv.gz. Test:
`bot/test_backtest_real_v3.py`.
"""
import math
import os

import numpy as np

from bot.backtest_real import (BREAKEVEN, VENTANA, EXPIRIES, EXP_REF,
                               _cargar_par, _frames_en, _regimen_de, _salida_idx, _wr)
from bot.backtest_real_v2 import _fecha_ms, _vetar, _rejilla, CORTE, GRID_CONF, MIN_SENALES_TRAIN
from bot.deep_analysis import DeepAnalyzer

FRACTAL_CORTES = (0.0, 0.80, 0.90, 0.96)     # cortes candidatos de alineación fractal
MIN_SUBGRUPO = 25                            # muestra mínima para fiarse de un subgrupo


def _sesion(hora_utc):
    """Sesión FX aproximada por hora UTC de la vela (para ver efecto de sesión)."""
    if 0 <= hora_utc < 7:
        return "asia"
    if 7 <= hora_utc < 13:
        return "europa"
    if 13 <= hora_utc < 21:
        return "eeuu"
    return "tarde"


def _n_conf(coinciden):
    """Nº de tiempos confirmados desde 'N/M tiempos' (para OPERAR, N==M)."""
    try:
        return int(str(coinciden).split("/")[0].strip())
    except (ValueError, IndexError):
        return 0


def _senales_meta(datos, analyzer, ts_m1, close_m1, idxs, ventana, expiries, filtros):
    """Como el _senales de v2 pero guardando metadata para estratificar: régimen,
    fractal, nº confirmados, sesión."""
    out = []
    for i in idxs:
        T = int(ts_m1[i]) + 60_000
        try:
            frames = _frames_en(datos, T, ventana)
            if 60 not in frames:
                continue
            reg = _regimen_de(frames)
            r = analyzer.analyze_frames(frames, regimen=reg)
        except Exception:
            continue
        v = r.get("veredicto", "")
        if not (v.endswith("OPERAR") and "NO OPERAR" not in v):
            continue
        d = r.get("direccion", "")
        lado = 1 if "CALL" in d else (-1 if "PUT" in d else 0)
        if lado == 0:
            continue
        if filtros and _vetar(frames):
            continue
        entrada = close_m1[i]
        res = {}
        for e in expiries:
            j = _salida_idx(ts_m1, int(ts_m1[i]) + e * 1000, tol_ms=120_000)
            if j is None:
                res[e] = None
                continue
            dif = close_m1[j] - entrada
            res[e] = "E" if dif == 0 else ("W" if (dif > 0) == (lado == 1) else "L")
        hora = int((int(ts_m1[i]) // 3_600_000) % 24)
        out.append({"lado": lado, "reg": reg or "nd",
                    "fractal": float(r.get("alineacion_fractal", 0.0)),
                    "n_conf": _n_conf(r.get("coinciden", "")),
                    "sesion": _sesion(hora), "exp": res})
    return out


def _wr_de(senales, exp):
    w = sum(1 for s in senales if s["exp"].get(exp) == "W")
    l = sum(1 for s in senales if s["exp"].get(exp) == "L")
    return _wr(w, l)


def _calibrar(datos, ts_m1, close_m1, train_idx, ventana, expiries, ref_exp):
    """min_conf con mejor win-rate en train (con filtros)."""
    an = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())))
    mejor = (0.18, None, 0)
    for mc in GRID_CONF:
        an.min_conf = mc
        sig = _senales_meta(datos, an, ts_m1, close_m1, train_idx, ventana, expiries, True)
        wr, _, n = _wr_de(sig, ref_exp)
        if n >= MIN_SENALES_TRAIN and wr is not None and (mejor[1] is None or wr > mejor[1]):
            mejor = (mc, wr, n)
    return mejor[0]


def _grupo(senales, clave):
    """Agrupa señales por el valor de una clave ('reg' | 'sesion' | 'n_conf')."""
    g = {}
    for s in senales:
        g.setdefault(s[clave], []).append(s)
    return g


def _elegir_regla(train_sig, ref_exp):
    """Elige, SOLO con train, la regla afinada: regímenes y sesiones cuyo win-rate de
    train supera el break-even con muestra suficiente, y el corte de fractal que
    maximiza el win-rate de train. Devuelve dict con la regla."""
    buenos_reg = set()
    for reg, sub in _grupo(train_sig, "reg").items():
        wr, _, n = _wr_de(sub, ref_exp)
        if wr is not None and n >= MIN_SUBGRUPO and wr > BREAKEVEN:
            buenos_reg.add(reg)
    buenas_ses = set()
    for ses, sub in _grupo(train_sig, "sesion").items():
        wr, _, n = _wr_de(sub, ref_exp)
        if wr is not None and n >= MIN_SUBGRUPO and wr > BREAKEVEN:
            buenas_ses.add(ses)
    mejor_frac, mejor_wr = 0.0, None
    for corte in FRACTAL_CORTES:
        sub = [s for s in train_sig if s["fractal"] >= corte]
        wr, _, n = _wr_de(sub, ref_exp)
        if wr is not None and n >= MIN_SUBGRUPO and (mejor_wr is None or wr > mejor_wr):
            mejor_frac, mejor_wr = corte, wr
    return {"reg": buenos_reg, "sesion": buenas_ses, "fractal": mejor_frac}


def _aplicar_regla(senales, regla):
    """Deja solo señales que cumplen la regla afinada. Un eje vacío = no filtra por él."""
    out = []
    for s in senales:
        if regla["reg"] and s["reg"] not in regla["reg"]:
            continue
        if regla["sesion"] and s["sesion"] not in regla["sesion"]:
            continue
        if s["fractal"] < regla["fractal"]:
            continue
        out.append(s)
    return out


def backtest_par_v3(par, destino="datasets/real", corte=CORTE, ventana=VENTANA,
                    train_n=250, test_n=400, expiries=EXPIRIES, ref_exp=EXP_REF):
    """Calibra + elige regla en train; devuelve señales de test crudas y filtradas."""
    datos = _cargar_par(par, destino)
    if 60 not in datos:
        return None
    ts_m1, df_m1 = datos[60]
    close_m1 = df_m1["close"].to_numpy(dtype=float)
    if len(ts_m1) < 500:
        return None
    tf_max, max_exp = max(datos.keys()), max(expiries)
    corte_ms = _fecha_ms(corte)
    train_idx = _rejilla(ts_m1, ts_m1[0], corte_ms, train_n, tf_max, ventana, max_exp)
    test_idx = _rejilla(ts_m1, corte_ms, ts_m1[-1], test_n, tf_max, ventana, max_exp)
    if len(train_idx) < 10 or len(test_idx) < 10:
        return None

    mc = _calibrar(datos, ts_m1, close_m1, train_idx, ventana, expiries, ref_exp)
    an = DeepAnalyzer(timeframes=tuple(sorted(datos.keys())), min_conf=mc)
    train_sig = _senales_meta(datos, an, ts_m1, close_m1, train_idx, ventana, expiries, True)
    test_sig = _senales_meta(datos, an, ts_m1, close_m1, test_idx, ventana, expiries, True)
    regla = _elegir_regla(train_sig, ref_exp)
    return {"par": par, "min_conf": mc, "regla": regla,
            "test": test_sig, "test_regla": _aplicar_regla(test_sig, regla)}


def _tabla(titulo, senales, clave, ref_exp):
    """Imprime win-rate por valor de una clave, sobre las señales de test."""
    print(f"\n{titulo} (expiry {ref_exp//60}m):")
    print(f"{'valor':<16}{'senales':>9}{'win-rate':>11}{'veredicto':>12}")
    for val, sub in sorted(_grupo(senales, clave).items(), key=lambda kv: -len(kv[1])):
        wr, margen, n = _wr_de(sub, ref_exp)
        if wr is None:
            print(f"{str(val):<16}{n:>9}{'s/senales':>11}")
            continue
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{str(val):<16}{n:>9}{wr:>10.1f}%{gana:>12}")


def _bloque_global(titulo, senales, expiries):
    print(f"\n{titulo}: {len(senales)} señales")
    print(f"{'expiry':>7}{'resueltas':>11}{'win-rate':>11}{'margen95':>11}  veredicto")
    for e in expiries:
        wr, margen, n = _wr_de(senales, e)
        if wr is None:
            print(f"{e//60:>5}m{n:>11}{'s/señales':>11}")
            continue
        gana = "GANA" if wr - margen > BREAKEVEN else (
               "PIERDE" if wr + margen < BREAKEVEN else "INCIERTO")
        print(f"{e//60:>5}m{n:>11}{wr:>10.2f}%{'±'+format(margen,'.2f'):>11}  {gana}")


def correr(destino="datasets/real", pares=None, corte=CORTE, train_n=250,
           test_n=400, expiries=EXPIRIES, ref_exp=EXP_REF):
    if not pares:
        from bot.profiles import REAL_PROFILE
        pares = list(REAL_PROFILE.activos)
    crudo, filtrado = [], []
    print(f"BACKTEST REAL v3 (afinado por régimen/sesión/fractal) sobre {destino}/")
    print(f"train hasta {corte}  ·  test desde {corte}  ·  break-even {BREAKEVEN:.2f}%")
    print("=" * 72)
    for par in pares:
        try:
            res = backtest_par_v3(par, destino, corte, VENTANA, train_n, test_n,
                                  expiries, ref_exp)
        except Exception as e:
            print(f"  {par:8} ERROR {e}")
            continue
        if not res:
            print(f"  {par:8} sin datos suficientes")
            continue
        crudo.extend(res["test"])
        filtrado.extend(res["test_regla"])
        rg = res["regla"]
        reg_txt = ",".join(sorted(rg["reg"])) or "todos"
        wr, _, n = _wr_de(res["test_regla"], ref_exp)
        wr_txt = f"{wr:.0f}%" if wr is not None else "n/d"
        print(f"  {par:8} conf={res['min_conf']:.2f} regla[reg={reg_txt} "
              f"fractal>={rg['fractal']:.2f}] -> test {n} señales {wr_txt}")

    print("=" * 72)
    _bloque_global("GLOBAL TEST CRUDO (sin afinar)", crudo, expiries)
    _bloque_global("GLOBAL TEST AFINADO (regla elegida en train)", filtrado, expiries)
    # Descriptivo: dónde vive el acierto en el test (para leer, no para elegir).
    _tabla("Descriptivo por REGIMEN", crudo, "reg", ref_exp)
    _tabla("Descriptivo por SESION", crudo, "sesion", ref_exp)
    _tabla("Descriptivo por Nº TIEMPOS confirmados", crudo, "n_conf", ref_exp)
    print("\n" + "=" * 72)
    print("CRUDO = todas las señales del test. AFINADO = solo las que cumplen la regla "
          "que ganó en train. Si AFINADO supera 52.08% con margen, hay borde real.")
    return crudo, filtrado


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Backtest REAL v3 (afinado).")
    ap.add_argument("pares", nargs="*", help="EURUSD ... (vacío = los 22)")
    ap.add_argument("--destino", default="datasets/real")
    ap.add_argument("--corte", default=CORTE)
    ap.add_argument("--train", type=int, default=250)
    ap.add_argument("--test", type=int, default=400)
    a = ap.parse_args()
    correr(a.destino, a.pares or None, a.corte, a.train, a.test)
