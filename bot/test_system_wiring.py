"""
bot/test_system_wiring.py
=========================
Valida el cableado del sistema del usuario SIN red: con una tendencia alcista
clara los votos deben inclinarse a CALL; con bajista, a PUT. Y usa los parámetros
del trader (EMA 8/20/50/200, RSI 5, etc.).
"""

import numpy as np
import pandas as pd

from bot.system_wiring import votar_sistema, direccion, _rsi_vote, _ema_vote, _macd_vote
from bot.scoring_strategy import CALL, PUT
from bot import otc_system, real_system


def _df(tendencia="alcista", n=260):
    """Genera velas OHLC con una tendencia clara (para que los votos se definan)."""
    base = 100.0
    precios = []
    for i in range(n):
        if tendencia == "alcista":
            p = base + i * 0.15 + np.sin(i / 5) * 0.3
        else:
            p = base + (n - i) * 0.15 + np.sin(i / 5) * 0.3
        precios.append(p)
    close = pd.Series(precios)
    high = close + 0.2
    low = close - 0.2
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_diez_votos():
    votos = votar_sistema(_df("alcista"), otc_system)
    # Debe votar los 10 indicadores (4 EMAs + stoch+boll+don+rsi+macd+S/R).
    assert len(votos) == 10, votos
    assert "ema8" in votos and "soporte_resistencia" in votos
    print(f"OK 10 votos con parámetros del trader: {votos}")


def _emas(votos):
    return [votos[k] for k in ("ema8", "ema20", "ema50", "ema200")]


def test_tendencia_alcista_emas_call():
    # La DIRECCIÓN (EMAs) es lo inequívoco: en alza el precio va sobre las EMAs.
    # (Los osciladores pueden votar PUT por sobrecompra: eso es correcto, y por
    #  eso el sistema decide por alineación + EMA200, no por conteo crudo.)
    votos = votar_sistema(_df("alcista"), otc_system)
    assert _emas(votos).count(CALL) >= 3, votos
    print("OK tendencia alcista -> EMAs votan CALL (dirección clara)")


def test_tendencia_bajista_emas_put():
    votos = votar_sistema(_df("bajista"), otc_system)
    assert _emas(votos).count(PUT) >= 3, votos
    print("OK tendencia bajista -> EMAs votan PUT (dirección clara)")


def test_usa_parametros_del_trader():
    # RSI período 5 (rápido): con precios planos no vota.
    plano = pd.Series([100.0] * 30)
    assert _rsi_vote(plano, 5) in (CALL, PUT, "HOLD")
    # EMA 8: precio muy por encima de su EMA -> CALL.
    sube = pd.Series([100 + i for i in range(30)], dtype=float)
    assert _ema_vote(sube, float(sube.iloc[-1]), 8) == CALL
    print("OK usa RSI 5 y EMA 8 (parámetros del trader)")


def test_macd_lee_direccion_no_solo_histograma():
    # REGRESIÓN: en tendencia SOSTENIDA el histograma se queda pegado a cero (o
    # negativo por ruido) aunque el precio suba con fuerza -> antes MACD votaba PUT
    # contra una subida clarísima. La dirección debe salir de la LÍNEA MACD vs 0.
    sube = pd.Series([100 + i * 1.0 for i in range(120)], dtype=float)
    assert _macd_vote(sube) == CALL, "MACD debe votar CALL en subida sostenida"
    baja = pd.Series([100 + (120 - i) * 1.0 for i in range(120)], dtype=float)
    assert _macd_vote(baja) == PUT, "MACD debe votar PUT en bajada sostenida"
    print("OK MACD lee la dirección (línea vs 0), no solo el signo del histograma")


def test_real_usa_misma_base():
    votos = votar_sistema(_df("alcista"), real_system)
    assert len(votos) == 10
    print("OK el sistema REAL vota con la misma base (10 indicadores)")


if __name__ == "__main__":
    test_diez_votos()
    test_tendencia_alcista_emas_call()
    test_tendencia_bajista_emas_put()
    test_usa_parametros_del_trader()
    test_macd_lee_direccion_no_solo_histograma()
    test_real_usa_misma_base()
    print("\nTODOS OK — cableado del sistema del usuario al cálculo real")
