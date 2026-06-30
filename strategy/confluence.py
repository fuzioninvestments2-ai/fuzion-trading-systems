"""
strategy/confluence.py
======================
Estrategia de CONFLUENCIA (EMA + RSI + Estocástico) para señales call/put.

IMPORTANTE (honestidad): esta estrategia codifica reglas de análisis técnico
ESTÁNDAR y DOCUMENTADAS. No garantiza rentabilidad. Su valor es ser clara,
parametrizable y MEDIBLE con el backtest incluido, para que las decisiones se
tomen con datos, no con fe.

Diseño (Reglas del proyecto):
  - Regla 1 (Modular): este módulo SOLO decide señales. SRP.
  - Regla 2 (Comentarios): se explica el PORQUÉ de cada condición.
  - SOLID: la decisión central es una función PURA (`evaluate_signal`), fácil de
    testear; `ConfluenceStrategy` la conecta con los indicadores en streaming.

------------------------------------------------------------------------------
LÓGICA (el "porqué" de cada condición)
------------------------------------------------------------------------------
Estrategia de REVERSIÓN a la media, adecuada para mercados OTC en rango:

  CALL (apostar a que SUBE) cuando hay SOBREVENTA girando al alza:
    - RSI <= rsi_oversold        -> el precio cayó "demasiado" (momento agotado)
    - %K cruza POR ENCIMA de %D  -> el estocástico empieza a girar arriba
    - %K en zona baja (<= stoch_oversold) -> el giro nace desde sobreventa

  PUT (apostar a que BAJA) es el espejo exacto en sobrecompra.

  Filtro de tendencia (opcional, EMA): si se activa, evitamos pelear contra una
  tendencia MUY marcada. Por defecto está DESACTIVADO porque en pura reversión
  el filtro puede anular señales válidas; lo dejamos como opción del usuario.

  Si no se cumple ninguna confluencia -> NONE (no operar). En binarias, NO
  operar es una decisión legítima y muchas veces la más rentable a largo plazo.
"""

from dataclasses import dataclass

import numpy as np

from indicators.ema import EMA
from indicators.rsi import RSI
from indicators.stochastic import Stochastic

# Señales posibles (constantes simples para evitar dependencias innecesarias).
CALL = "CALL"
PUT = "PUT"
NONE = "NONE"


@dataclass
class StrategyConfig:
    """Parámetros ajustables de la estrategia (el usuario los puede tunear)."""
    ema_period: int = 20
    rsi_period: int = 14
    stoch_k: int = 14
    stoch_smooth: int = 3
    stoch_d: int = 3
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    use_trend_filter: bool = False   # EMA como filtro de tendencia (opcional)


def evaluate_signal(price, ema, rsi, k, d, prev_k, prev_d, cfg):
    """
    Función PURA: dada una "foto" de los indicadores, devuelve CALL/PUT/NONE.

    Recibe los valores ya calculados (inyección de dependencias) -> es trivial
    de testear de forma determinista sin simular cientos de ticks.

    Parámetros (pueden ser None si el indicador aún no tiene datos):
      price   : precio actual
      ema     : valor EMA actual (para filtro de tendencia opcional)
      rsi     : valor RSI actual
      k, d    : %K y %D actuales del estocástico
      prev_k, prev_d : %K y %D del paso anterior (para detectar el CRUCE)
      cfg     : StrategyConfig
    """
    # Sin datos suficientes -> no arriesgamos: NONE. (Honesto y prudente.)
    if None in (rsi, k, d, prev_k, prev_d):
        return NONE

    # Detección de CRUCE del estocástico usando el valor anterior y el actual:
    #   cruce al alza  : antes %K <= %D y ahora %K > %D
    #   cruce a la baja: antes %K >= %D y ahora %K < %D
    cross_up = prev_k <= prev_d and k > d
    cross_down = prev_k >= prev_d and k < d

    # Filtro de tendencia opcional con la EMA.
    trend_ok_for_call = True
    trend_ok_for_put = True
    if cfg.use_trend_filter and ema is not None and price is not None:
        # En CALL evitamos operar muy por debajo de la EMA (tendencia bajista
        # fuerte); en PUT, lo simétrico. Es un filtro suave, no estricto.
        trend_ok_for_call = price >= ema
        trend_ok_for_put = price <= ema

    # CALL: sobreventa (RSI bajo) + estocástico girando al alza desde zona baja.
    if (rsi <= cfg.rsi_oversold
            and cross_up
            and k <= cfg.stoch_oversold
            and trend_ok_for_call):
        return CALL

    # PUT: sobrecompra (RSI alto) + estocástico girando a la baja desde zona alta.
    if (rsi >= cfg.rsi_overbought
            and cross_down
            and k >= cfg.stoch_overbought
            and trend_ok_for_put):
        return PUT

    return NONE


class ConfluenceStrategy:
    """
    Conecta los indicadores reales en STREAMING con la decisión pura.

    SRP: orquesta indicadores y delega la decisión en `evaluate_signal`. No sabe
    de red ni de Telegram. Estado encapsulado (sin globales mutables).
    """

    def __init__(self, cfg=None):
        self.cfg = cfg or StrategyConfig()
        self._ema = EMA(self.cfg.ema_period)
        self._rsi = RSI(self.cfg.rsi_period)
        self._stoch = Stochastic(self.cfg.stoch_k, self.cfg.stoch_smooth,
                                 self.cfg.stoch_d)
        self._prev_k = None
        self._prev_d = None

    def update(self, price):
        """Procesa un tick y devuelve la señal (CALL/PUT/NONE) de ese tick."""
        price = float(price)
        ema_val = self._ema.update(price)
        rsi_val = self._rsi.update(price)
        k_val, d_val = self._stoch.update(price)

        signal = evaluate_signal(
            price, ema_val, rsi_val, k_val, d_val,
            self._prev_k, self._prev_d, self.cfg)

        # Guardamos %K/%D para detectar el cruce en el PRÓXIMO tick.
        self._prev_k, self._prev_d = k_val, d_val
        return signal


def backtest(prices, expiry_horizon=3, cfg=None):
    """
    Evalúa la estrategia sobre una serie de precios YA conocida.

    HONESTIDAD: esto mide el comportamiento sobre ESTOS datos concretos. NO
    predice el futuro ni garantiza resultados en vivo. Es una herramienta para
    inspeccionar la lógica con evidencia.

    Para cada señal en el índice i, el "resultado" en opciones binarias se mide
    comparando el precio de expiración (i + expiry_horizon) con el de entrada:
      - CALL gana si price[i+h] > price[i]
      - PUT  gana si price[i+h] < price[i]

    Devuelve un dict con conteos y win-rate observado (sobre estos datos).
    """
    prices = np.asarray(prices, dtype=np.float64)
    cfg = cfg or StrategyConfig()
    strat = ConfluenceStrategy(cfg)

    signals = []
    for i, p in enumerate(prices):
        signals.append(strat.update(p))

    wins = losses = ties = total = 0
    for i, sig in enumerate(signals):
        if sig == NONE:
            continue
        j = i + expiry_horizon
        if j >= len(prices):
            break                       # sin datos de expiración -> no contar
        entry, exit_ = prices[i], prices[j]
        if sig == CALL:
            won = exit_ > entry
        else:                            # PUT
            won = exit_ < entry
        tie = exit_ == entry
        total += 1
        if tie:
            ties += 1
        elif won:
            wins += 1
        else:
            losses += 1

    decided = wins + losses
    win_rate = (wins / decided) if decided > 0 else None
    return {
        "total_signals": total,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": win_rate,          # None si no hubo operaciones decididas
        "calls": signals.count(CALL),
        "puts": signals.count(PUT),
    }
