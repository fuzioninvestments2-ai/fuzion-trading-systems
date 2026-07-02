"""
bot/test_trend_filter.py
=======================
Valida el FILTRO DE TENDENCIA MAYOR: una señal que va contra la temporalidad más
larga confirmada se baja de categoría y se avisa. Sin red, determinista.
"""

from bot.deep_analysis import DeepAnalyzer
from bot.scoring_strategy import CALL, PUT


def _op(direccion, conf, confirmado=True):
    """Crea la opinión de una temporalidad."""
    return {"dir": direccion, "conf": conf, "velas": 30, "votes": {},
            "confirmado": confirmado, "datos": True}


def test_a_favor_de_tendencia_no_baja():
    da = DeepAnalyzer()
    # Cortos y el largo TODOS DOWN -> a favor de la tendencia, sin penalización.
    por = {15: _op(PUT, 0.4), 60: _op(PUT, 0.4), 1800: _op(PUT, 0.4)}
    r = da._combinar(por)
    assert not r.get("contra_tendencia")
    assert "CONTRA" not in r["explicacion"].upper()
    print(f"OK a favor de la tendencia -> {r['veredicto']} (sin penalización)")


def test_contra_tendencia_baja_categoria():
    da = DeepAnalyzer()
    # Cortos DOWN pero el tiempo MÁS LARGO (30m) UP -> señal PUT contra tendencia.
    por = {15: _op(PUT, 0.4), 30: _op(PUT, 0.4), 60: _op(PUT, 0.4),
           300: _op(PUT, 0.4), 1800: _op(CALL, 0.4)}
    r = da._combinar(por)
    assert r["contra_tendencia"] is True
    assert "CONTRA la tendencia mayor" in r["explicacion"]
    # 4/5 DOWN daría OPERAR/OPCIONAL; contra tendencia lo baja.
    assert r["veredicto"] in ("🟡 OPCIONAL", "🚫 NO OPERAR")
    print(f"OK contra tendencia -> baja a {r['veredicto']} + aviso")


def test_operar_limpio_se_mantiene():
    da = DeepAnalyzer()
    # Todos DOWN incluido el más largo -> OPERAR limpio, sin penalización.
    por = {15: _op(PUT, 0.5), 60: _op(PUT, 0.5), 300: _op(PUT, 0.5),
           1800: _op(PUT, 0.5)}
    r = da._combinar(por)
    assert not r.get("contra_tendencia")
    assert r["veredicto"] == "✅ OPERAR"
    print("OK señal alineada con la tendencia -> OPERAR se mantiene")


def test_tendencia_es_el_tiempo_mas_largo():
    da = DeepAnalyzer()
    # El desacuerdo en un tiempo CORTO no penaliza (solo el más largo es tendencia).
    por = {15: _op(CALL, 0.4), 60: _op(PUT, 0.4), 300: _op(PUT, 0.4),
           1800: _op(PUT, 0.4)}
    r = da._combinar(por)
    # side=PUT (mayoría) y el más largo (1800) también PUT -> a favor, sin aviso.
    assert not r.get("contra_tendencia")
    print("OK el desacuerdo en un tiempo corto no cuenta como contra-tendencia")


if __name__ == "__main__":
    test_a_favor_de_tendencia_no_baja()
    test_contra_tendencia_baja_categoria()
    test_operar_limpio_se_mantiene()
    test_tendencia_es_el_tiempo_mas_largo()
    print("\nTODOS OK — filtro de tendencia mayor (ecuación de tiempo)")
