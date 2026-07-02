"""
bot/test_weights_dynamic.py
===========================
Valida que la configuración de indicadores NO sea fija: cambia por TIEMPO y por
RÉGIMEN (Oscillate/Slide), como pidió el usuario. Sin red, determinista.
"""

import numpy as np
import pandas as pd

from bot.scoring_strategy import (BASE_WEIGHTS, weights_for, ScoringStrategy,
                                  _factor_por_tiempo, _factor_por_regimen)
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


if __name__ == "__main__":
    test_base_sin_ajuste()
    test_por_tiempo_corto_vs_largo()
    test_por_regimen_slide_vs_oscillate()
    test_combinado_multiplica()
    test_analyze_acepta_pesos()
    print("\nTODOS OK — configuración de indicadores por tiempo/régimen")
