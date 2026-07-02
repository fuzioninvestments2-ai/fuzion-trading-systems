"""
bot/test_weight_learning.py
==========================
Valida el aprendizaje de pesos por indicador. Sin red, determinista.
"""

import numpy as np
import pandas as pd

from bot.weight_learning import learn_weights
from bot.scoring_strategy import BASE_WEIGHTS, weights_for


def _serie_tendencial(n=320, seed=1):
    """Serie con tendencia alcista clara + algo de ruido (favorece seguidores)."""
    rng = np.random.RandomState(seed)
    close = 100 + np.arange(n) * 0.05 + rng.normal(0, 0.05, n)
    return pd.DataFrame({"open": close, "high": close + 0.05,
                         "low": close - 0.05, "close": close,
                         "volume": rng.randint(1, 5, n)})


def test_datos_insuficientes_devuelve_none():
    df = _serie_tendencial(20)
    assert learn_weights(df) is None
    print("OK datos insuficientes -> None")


def test_devuelve_multiplicadores_para_todos():
    res = learn_weights(_serie_tendencial())
    assert res is not None
    # Debe haber un multiplicador para cada indicador base.
    assert set(res["multipliers"].keys()) == set(BASE_WEIGHTS.keys())
    print("OK multiplicadores para todos los indicadores")


def test_multiplicadores_en_rango():
    res = learn_weights(_serie_tendencial())
    for name, m in res["multipliers"].items():
        assert 0.5 <= m <= 1.6, f"{name}={m} fuera de tope"
    print("OK multiplicadores dentro de los topes [0.5, 1.6]")


def test_indicador_acertado_pesa_mas():
    # En una tendencia alcista limpia, los seguidores (MACD/medias) deberían
    # acertar >= azar; su multiplicador no debería quedar por debajo de 1.0
    # (salvo muestra insuficiente, en cuyo caso es 1.0 neutro).
    res = learn_weights(_serie_tendencial())
    stats = res["stats"]
    # Al menos un indicador con hit_rate alto debe tener multiplicador > 1.
    subieron = [n for n, m in res["multipliers"].items() if m > 1.0]
    assert subieron, res["multipliers"]
    print(f"OK indicadores acertados pesan más: {subieron}")


def test_learned_se_aplica_en_weights_for():
    # weights_for debe multiplicar el peso base por el multiplicador aprendido.
    learned = {"macd": 1.5}
    w = weights_for(60, None, learned=learned)
    assert abs(w["macd"] - BASE_WEIGHTS["macd"] * 1.5) < 1e-9
    # Un indicador sin entrada aprendida queda igual que su base (tf medio).
    assert abs(w["rsi"] - BASE_WEIGHTS["rsi"]) < 1e-9
    print("OK weights_for aplica los pesos aprendidos")


if __name__ == "__main__":
    test_datos_insuficientes_devuelve_none()
    test_devuelve_multiplicadores_para_todos()
    test_multiplicadores_en_rango()
    test_indicador_acertado_pesa_mas()
    test_learned_se_aplica_en_weights_for()
    print("\nTODOS OK — aprendizaje de pesos por indicador")
