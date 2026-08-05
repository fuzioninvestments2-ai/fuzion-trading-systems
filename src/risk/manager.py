"""
src/risk/manager.py
===================
FASE 2: Gestor de RIESGO (disciplina y proteccion) para el bot de senales.

ADVERTENCIA DE ALCANCE (honestidad del proyecto): Fuzion es un bot de SENALES
educativas, solo lectura, NO coloca ordenes. Este modulo por tanto es ADVISORY:
calcula tamano sugerido, stop sugerido y decide cuando NO habilitar mas senales
del dia. La ejecucion siempre la hace el humano. Nada aqui envia ordenes.

Reune, en una sola pieza, las 5 protecciones del manual:
  1. Position sizing (2% del capital por trade).
  2. Stop-loss dinamico por ATR (volatilidad real, no un % fijo arbitrario).
  3. Circuit breaker: si el drawdown del DIA supera 5%, se corta (STOP).
  4. Tope de trades por dia por par (evita sobre-operar el mismo activo).
  5. Anti-manipulacion (spikes + gaps) antes de habilitar una senal.

Regla 1 (no duplicar): el anti-manipulacion de SPIKES/volatilidad ya existe y
esta probado en `bot/manipulation.py`; aqui se COMPONE `ManipulationGuard` en
vez de reimplementarlo. Este modulo solo agrega lo que faltaba: ATR, stop
dinamico, circuit breaker diario, tope por par y deteccion de GAPS.

SRP: solo decide riesgo. No conecta a red, no coloca ordenes. Se prueba sin red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from bot.manipulation import ManipulationGuard


class TradeDecision(Enum):
    """
    Veredicto de riesgo sobre una senal. PORQUE: no es binario; a veces la senal
    es valida pero el contexto pide entrar con MENOS tamano en vez de bloquear.
      - ALLOW : condiciones sanas, tamano completo.
      - REDUCE: valida pero con reservas (recovery o contexto marginal) -> mitad.
      - BLOCK : algun filtro de proteccion la rechaza; NO operar.
    """
    ALLOW = "ALLOW"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class MarketCondition:
    """
    Foto del CONTEXTO de mercado al momento de la senal (todo en pips salvo los
    flags). Es entrada de `assess_signal`; el modulo no la calcula (la aporta el
    servicio que ya mide spread, ATR y S/R).
    """
    spread_pips: float                     # coste de entrada; ancho = mala ejecucion
    atr_pips: float                        # volatilidad real reciente
    distance_to_nearest_sr: float          # distancia al soporte/resistencia mas cercano
    session: str = ""                      # "Londres"/"NuevaYork"/"Asia"... informativo
    is_news_event: bool = False            # noticia de alto impacto en curso
    volume_anomaly: bool = False           # volumen anomalo (posible manipulacion)
    gap_detected: bool = False             # hueco de precio detectado


@dataclass(frozen=True)
class RiskAssessment:
    """Resultado de evaluar una senal: veredicto + porque + tamano sugerido."""
    decision: TradeDecision
    reason: str
    size: float = 0.0                      # monto sugerido (0 si BLOCK)
    probability: float = 0.0
    pair: str = ""
    direction: str = ""
    is_recovery: bool = False
    details: Dict[str, object] = field(default_factory=dict)


def average_true_range(high: Sequence[float], low: Sequence[float],
                       close: Sequence[float], period: int = 14) -> float:
    """
    ATR (Average True Range) por suavizado de Wilder.

    PORQUE: el stop debe respirar con la volatilidad REAL del activo. Un stop de
    "% fijo" es demasiado ancho en calma y demasiado justo en agitacion; el ATR
    mide el rango tipico reciente y ajusta el stop a la realidad del mercado.

    True Range de cada vela = max(
        high-low,
        |high - close_prev|,
        |low  - close_prev|
    ), que captura tambien los gaps entre velas (por eso usa el cierre previo).
    Devuelve el ATR (float). Si no hay datos suficientes, devuelve 0.0.
    """
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    n = close.size
    if n < 2 or high.size != n or low.size != n:
        return 0.0

    prev_close = close[:-1]
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - prev_close),
        np.abs(low[1:] - prev_close),
    ])
    if tr.size == 0:
        return 0.0

    period = max(1, min(period, tr.size))
    # Wilder: primer ATR = media simple de los primeros `period` TR; luego se
    # suaviza recursivamente. Con pocos datos, cae a la media simple del tramo.
    atr = float(np.mean(tr[:period]))
    for x in tr[period:]:
        atr = (atr * (period - 1) + float(x)) / period
    return atr


class RiskManager:
    """
    Gestor de riesgo advisory. Todo su estado es del DIA en curso; `reset_dia`
    lo reinicia. No persiste ni toca red.
    """

    def __init__(self, capital: float = 1000.0, risk_per_trade: float = 0.02,
                 max_daily_drawdown: float = 0.05, max_trades_por_par: int = 3,
                 atr_period: int = 14, atr_stop_mult: float = 1.5,
                 gap_umbral_pct: float = 0.004,
                 min_probability: float = 90.0,
                 max_spread_pips: float = 3.0,
                 min_atr_pips: float = 3.0, max_atr_pips: float = 40.0,
                 min_dist_sr_pips: float = 8.0,
                 manipulation_guard: Optional[ManipulationGuard] = None) -> None:
        if capital <= 0:
            raise ValueError("capital debe ser > 0")
        if not 0 < risk_per_trade <= 0.5:
            raise ValueError("risk_per_trade fuera de rango (0, 0.5]")
        if not 0 < max_daily_drawdown < 1:
            raise ValueError("max_daily_drawdown fuera de rango (0, 1)")

        self.capital_inicial = float(capital)
        self.risk_per_trade = float(risk_per_trade)      # 2% por defecto
        self.max_daily_drawdown = float(max_daily_drawdown)  # 5% por defecto
        self.max_trades_por_par = int(max_trades_por_par)
        self.atr_period = int(atr_period)
        self.atr_stop_mult = float(atr_stop_mult)
        self.gap_umbral_pct = float(gap_umbral_pct)       # 0.4% salto = gap

        # Umbrales de `assess_signal`. PORQUE: el motor cuantico exige 90%+; el
        # resto son filtros de contexto (spread, volatilidad, cercania a S/R)
        # que protegen de entradas de mala calidad aun con probabilidad alta.
        self.min_probability = float(min_probability)     # 90% (motor cuantico)
        self.max_spread_pips = float(max_spread_pips)     # spread ancho = mala ejecucion
        self.min_atr_pips = float(min_atr_pips)           # por debajo: mercado muerto
        self.max_atr_pips = float(max_atr_pips)           # por encima: volatilidad extrema
        self.min_dist_sr_pips = float(min_dist_sr_pips)   # pegado a soporte/resistencia

        # Composicion (Regla 1): reutiliza el guardian ya probado.
        self.guard = manipulation_guard or ManipulationGuard()

        self.reset_dia()

    def set_capital(self, capital: float) -> None:
        """
        Fija el capital de la cuenta y rebasa la linea del dia a ese valor.
        PORQUE: el sizing (2%) y el drawdown se miden sobre el capital vigente;
        se llama al arrancar (o al recargar la cuenta) antes de operar.
        """
        if capital <= 0:
            raise ValueError("capital debe ser > 0")
        self.capital_inicial = float(capital)
        self.reset_dia()

    # ------------------------------------------------------------------ estado
    def reset_dia(self) -> None:
        """Reinicia el estado del dia (equity, pico, contadores por par)."""
        self.equity = self.capital_inicial
        self.peak_equity = self.capital_inicial          # pico del dia (drawdown)
        self.trades_por_par: Dict[str, int] = {}
        self.trades_dia = 0

    # ------------------------------------------------------ 1. position sizing
    def position_size(self, capital: Optional[float] = None) -> float:
        """
        Monto sugerido por trade = 2% del capital (o del equity actual si se
        omite). PORQUE: arriesgar una fraccion pequena y constante alarga la
        vida de la cuenta y deja que la estadistica trabaje.
        """
        base = self.equity if capital is None else float(capital)
        return round(base * self.risk_per_trade, 2)

    # ------------------------------------------------- 2. stop-loss por ATR
    def stop_loss_dinamico(self, entry: float, direccion: str,
                           high: Sequence[float], low: Sequence[float],
                           close: Sequence[float]) -> Optional[float]:
        """
        Precio de stop sugerido = entry -/+ ATR * multiplicador, segun direccion.

        CALL (apuesta al alza): el stop va DEBAJO del precio de entrada.
        PUT  (apuesta a la baja): el stop va ENCIMA.
        Devuelve None si no hay ATR (datos insuficientes).
        """
        atr = average_true_range(high, low, close, self.atr_period)
        if atr <= 0:
            return None
        dist = atr * self.atr_stop_mult
        d = direccion.upper()
        if d in ("CALL", "BUY", "UP"):
            return round(entry - dist, 8)
        if d in ("PUT", "SELL", "DOWN"):
            return round(entry + dist, 8)
        raise ValueError(f"direccion invalida: {direccion}")

    # ------------------------------------------------ 3. circuit breaker diario
    def drawdown_actual(self) -> float:
        """Drawdown del dia como fraccion desde el pico (0.0 = sin caida)."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)

    def circuit_breaker(self) -> Tuple[bool, str]:
        """
        (permitido, motivo). Si el drawdown del dia supera el maximo (5%), corta:
        no se habilitan mas senales hasta `reset_dia`. PORQUE: frenar tras una
        mala racha evita el pozo emocional de "recuperar" arriesgando mas.
        """
        dd = self.drawdown_actual()
        if dd > self.max_daily_drawdown:
            return False, f"circuit breaker: drawdown {dd:.1%} > {self.max_daily_drawdown:.0%}"
        return True, "ok"

    # ---------------------------------------------- 4. tope de trades por par
    def _tope_par_ok(self, par: str) -> Tuple[bool, str]:
        usados = self.trades_por_par.get(par, 0)
        if usados >= self.max_trades_por_par:
            return False, f"tope de {self.max_trades_por_par} trades/dia alcanzado en {par}"
        return True, "ok"

    # --------------------------------------------- 5. anti-manipulacion (gaps)
    def detectar_gap(self, prices: Sequence[float]) -> bool:
        """
        Gap = salto brusco entre dos precios consecutivos que supera el umbral
        relativo. PORQUE: un hueco grande suele ser feed roto o barrida
        fabricada; entrar justo ahi es ruleta. Complementa los SPIKES que ya
        detecta `ManipulationGuard` (que mira picos que rebotan, no huecos secos).
        """
        p = np.asarray(prices, dtype=np.float64)
        if p.size < 2:
            return False
        prev = p[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.abs(np.diff(p)) / np.where(prev == 0, np.nan, np.abs(prev))
        return bool(np.nanmax(rel) > self.gap_umbral_pct)

    def anti_manipulacion(self, prices: Sequence[float]) -> Tuple[bool, List[str]]:
        """(limpio, razones). Combina spikes/volatilidad (guard) + gaps."""
        res = self.guard.check(prices)
        razones = list(res.get("reasons", []))
        if self.detectar_gap(prices):
            razones.append("gap de precio anormal")
        return (len(razones) == 0), razones

    # -------------------------------------------------- decision integrada
    def puede_operar(self, par: str,
                     prices: Optional[Sequence[float]] = None) -> Tuple[bool, str]:
        """
        Chequeo unico antes de habilitar una senal. Orden barato->caro:
        circuit breaker -> tope por par -> anti-manipulacion.
        """
        ok, motivo = self.circuit_breaker()
        if not ok:
            return False, motivo

        ok, motivo = self._tope_par_ok(par)
        if not ok:
            return False, motivo

        if prices is not None:
            limpio, razones = self.anti_manipulacion(prices)
            if not limpio:
                return False, "anti-manipulacion: " + ", ".join(razones)

        return True, "ok"

    # ---------------------------------------------- evaluacion de senal (alto nivel)
    @staticmethod
    def _norm_prob(probability: float) -> float:
        """
        Normaliza la probabilidad a escala 0-100. PORQUE: unas partes del sistema
        la manejan como fraccion (0.92) y otras como porcentaje (92); si llega
        <=1 se asume fraccion y se escala, evitando bloquear todo por error.
        """
        p = float(probability)
        return p * 100.0 if 0.0 < p <= 1.0 else p

    def assess_signal(self, pair: str, direction: str, probability: float,
                      market: MarketCondition,
                      is_recovery: bool = False) -> RiskAssessment:
        """
        Veredicto de riesgo de una senal concreta, combinando el estado del dia
        (circuit breaker, tope por par) con el CONTEXTO de mercado (spread, ATR,
        S/R, noticias, gaps). Devuelve un RiskAssessment con decision + porque.

        `is_recovery`: senal que busca recuperar una perdida previa. NO es
        martingala (no se dobla el tamano — eso esta prohibido); al reves, se
        exige mas probabilidad y se REDUCE el tamano. Es la disciplina que evita
        el pozo de "recuperar" arriesgando de mas.
        """
        prob = self._norm_prob(probability)
        det: Dict[str, object] = {"session": market.session, "atr_pips": market.atr_pips,
                                  "spread_pips": market.spread_pips,
                                  "dist_sr": market.distance_to_nearest_sr}

        def block(reason: str) -> RiskAssessment:
            return RiskAssessment(TradeDecision.BLOCK, reason, 0.0, prob, pair,
                                  direction, is_recovery, det)

        # --- Bloqueos duros (baratos primero) -------------------------------
        # 1) Direccion valida: solo CALL/PUT operan; HOLD u otra -> no hay senal.
        d = str(direction).upper()
        if d not in ("CALL", "PUT", "BUY", "SELL"):
            return block(f"sin direccion operable ({direction})")

        # 2) Estado del dia: circuit breaker y tope por par (protecciones ya probadas).
        ok, motivo = self.circuit_breaker()
        if not ok:
            return block(motivo)
        ok, motivo = self._tope_par_ok(pair)
        if not ok:
            return block(motivo)

        # 3) Filtros de contexto que son manipulacion/ruido: no se opera ahi.
        if market.is_news_event:
            return block("noticia de alto impacto en curso")
        if market.gap_detected:
            return block("gap de precio detectado")
        if market.volume_anomaly:
            return block("volumen anomalo (posible manipulacion)")

        # 4) Calidad de ejecucion / mercado.
        if market.spread_pips > self.max_spread_pips:
            return block(f"spread {market.spread_pips} > {self.max_spread_pips} pips")
        if market.atr_pips < self.min_atr_pips:
            return block(f"ATR {market.atr_pips} < {self.min_atr_pips} pips (mercado muerto)")
        if market.atr_pips > self.max_atr_pips:
            return block(f"ATR {market.atr_pips} > {self.max_atr_pips} pips (volatilidad extrema)")
        if market.distance_to_nearest_sr < self.min_dist_sr_pips:
            return block(f"pegado a S/R ({market.distance_to_nearest_sr} < "
                         f"{self.min_dist_sr_pips} pips)")

        # 5) Probabilidad del motor. En recovery se exige un plus (mas estricto).
        umbral = self.min_probability + (3.0 if is_recovery else 0.0)
        if prob < umbral:
            return block(f"probabilidad {prob:.1f}% < {umbral:.1f}% requerido")

        # --- Pasa: ALLOW o REDUCE -------------------------------------------
        base_size = self.position_size()
        # Recovery o contexto marginal -> media posicion (nunca mas).
        marginal = prob < (umbral + 3.0) or market.atr_pips > (0.8 * self.max_atr_pips)
        if is_recovery or marginal:
            razon = "recovery: media posicion" if is_recovery else "contexto marginal: media posicion"
            return RiskAssessment(TradeDecision.REDUCE, razon, round(base_size / 2.0, 2),
                                  prob, pair, d, is_recovery, det)

        return RiskAssessment(TradeDecision.ALLOW, "condiciones sanas", base_size,
                              prob, pair, d, is_recovery, det)

    # -------------------------------------------------- registro de resultado
    def registrar_trade(self, par: str, pnl: float) -> None:
        """
        Registra el resultado de una operacion (para backtest/disciplina del
        dia): actualiza equity, pico y el contador por par.
        """
        self.equity += float(pnl)
        self.trades_dia += 1
        self.trades_por_par[par] = self.trades_por_par.get(par, 0) + 1
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
