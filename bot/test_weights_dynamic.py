"""
bot/test_weights_dynamic.py
===========================
Valida que la configuración de indicadores NO sea fija: cambia por TIEMPO y por
RÉGIMEN (Oscillate/Slide), como pidió el usuario. Sin red, determinista.
"""

import numpy as np
import pandas as pd

from bot.scoring_strategy import (BASE_WEIGHTS, weights_for, ScoringStrategy,
                                  _factor_por_tiempo, _factor_por_regimen,
                                  _vwap_vote, _pattern_vote, CALL, PUT, HOLD)
from bot.config import TradingConfig


def test_base_sin_ajuste():
    # Sin tiempo ni régimen -> pesos base intactos.
    assert weights_for(None, None) == BASE_WEIGHTS
    print("OK base sin ajuste")


def test_por_tiempo_corto_vs_largo():
    corto = weights_for(15, None)
    largo = weights_for(1800, None)
    # En corto las medias pesan MENOS que en largo (SMA200 no tiene velas).
    assert corto["moving_averages"] < BASE_WEIGHTS["moving_averages"]
    assert largo["moving_averages"] > BASE_WEIGHTS["moving_averages"]
    # En corto el estocástico rápido pesa MÁS que en largo.
    assert corto["stochastic"] > largo["stochastic"]
    print("OK pesos por tiempo (corto vs largo)")


def test_por_regimen_slide_vs_oscillate():
    slide = weights_for(60, "slide")
    osc = weights_for(60, "oscillate")
    # En tendencia (slide) MACD manda; en rango (oscillate) pesa menos.
    assert slide["macd"] > osc["macd"]
    # En rango (oscillate) los rebotes (RSI/Bollinger) mandan; en tendencia menos.
    assert osc["rsi"] > slide["rsi"]
    assert osc["bollinger"] > slide["bollinger"]
    print("OK pesos por régimen (slide vs oscillate)")


def test_combinado_multiplica():
    # Los factores de tiempo y régimen se combinan (multiplican) sobre la base.
    w = weights_for(1800, "slide")
    esperado = (BASE_WEIGHTS["macd"]
                * _factor_por_tiempo(1800).get("macd", 1.0)
                * _factor_por_regimen("slide").get("macd", 1.0))
    assert abs(w["macd"] - esperado) < 1e-9
    print("OK factores tiempo+régimen se multiplican")


def test_analyze_acepta_pesos():
    # ScoringStrategy.analyze debe aceptar pesos custom sin romper.
    rng = np.arange(60, dtype=float)
    close = pd.Series(100 + np.sin(rng / 3.0))
    df = pd.DataFrame({"open": close, "high": close + 0.05,
                       "low": close - 0.05, "close": close})
    cfg = TradingConfig(stack_method="aggressive")
    s = ScoringStrategy(cfg)
    sig1, c1, _ = s.analyze(df)                          # base
    sig2, c2, _ = s.analyze(df, weights=weights_for(15, "oscillate"))
    # Ambas devuelven algo válido; con pesos distintos la confianza puede diferir.
    assert 0.0 <= c1 <= 1.0 and 0.0 <= c2 <= 1.0
    print(f"OK analyze con pesos custom (conf base={c1:.3f}, ajustada={c2:.3f})")


def test_vwap_y_patterns_son_indicadores():
    # Ambos nuevos votantes deben estar en los pesos base.
    assert "vwap" in BASE_WEIGHTS and "patterns" in BASE_WEIGHTS
    print("OK vwap y patterns están en los pesos base")


def test_vwap_vota():
    # Serie que sube: precio por encima del VWAP -> voto CALL.
    velas = [(100 + i, 100 + i, 100 + i, 100 + i) for i in range(12)]
    df = pd.DataFrame(velas, columns=["open", "high", "low", "close"])
    side, fuerza = _vwap_vote(df)
    assert side == CALL and fuerza > 0.5
    print(f"OK VWAP vota (CALL, fuerza={fuerza:.2f})")


def test_patterns_vota_y_doji_no():
    # Martillo -> voto CALL.
    mar = pd.DataFrame([(100.0, 100.15, 98.0, 100.1)],
                       columns=["open", "high", "low", "close"])
    side, _ = _pattern_vote(mar)
    assert side == CALL
    # Doji -> NO vota (indecisión).
    doji = pd.DataFrame([(100, 101, 99, 100.02)],
                        columns=["open", "high", "low", "close"])
    side_d, _ = _pattern_vote(doji)
    assert side_d == HOLD
    print("OK patrones votan; el doji se abstiene (indecisión)")


def test_analyze_incluye_nuevos_votos():
    rng = pd.Series(range(60))
    close = 100 + rng * 0.1
    df = pd.DataFrame({"open": close, "high": close + 0.05,
                       "low": close - 0.05, "close": close,
                       "volume": [3] * 60})
    _, _, det = ScoringStrategy(TradingConfig()).analyze(df)
    assert "vwap" in det["votes"] and "patterns" in det["votes"]
    print(f"OK analyze incluye votos vwap={det['votes']['vwap']} "
          f"patterns={det['votes']['patterns']}")


if __name__ == "__main__":
    test_base_sin_ajuste()
    test_por_tiempo_corto_vs_largo()
    test_por_regimen_slide_vs_oscillate()
    test_combinado_multiplica()
    test_analyze_acepta_pesos()
    test_vwap_y_patterns_son_indicadores()
    test_vwap_vota()
    test_patterns_vota_y_doji_no()
    test_analyze_incluye_nuevos_votos()
    print("\nTODOS OK — configuración de indicadores por tiempo/régimen")
