"""
Greeks Calculator — Black-Scholes completo.
Newton-Raphson IV solver con fallback a Brent.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional
from scipy.stats import norm
from scipy.optimize import brentq


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float = 0.0


@dataclass
class OptionLeg:
    option_type: str    # "call" | "put"
    qty: int            # positivo = long, negativo = short
    S: float
    K: float
    T: float
    r: float
    sigma: float


@dataclass
class PositionGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    legs: int


class GreeksCalculator:

    @staticmethod
    def _d1_d2(S: float, K: float, T: float, r: float, sigma: float):
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.0, 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    def calculate_all_greeks(self, S: float, K: float, T: float, r: float,
                              sigma: float, option_type: str) -> Greeks:
        if T <= 0:
            intrinsic = max(S - K, 0) if option_type == "call" else max(K - S, 0)
            delta = 1.0 if option_type == "call" and S > K else (
                -1.0 if option_type == "put" and S < K else 0.0)
            return Greeks(delta=delta, gamma=0, theta=0, vega=0, rho=0)

        d1, d2 = self._d1_d2(S, K, T, r, sigma)
        n_d1 = norm.pdf(d1)
        sqrt_T = math.sqrt(T)

        if option_type == "call":
            delta = norm.cdf(d1)
            rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100
            theta = (-(S * n_d1 * sigma) / (2 * sqrt_T)
                     - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365
        else:
            delta = norm.cdf(d1) - 1
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100
            theta = (-(S * n_d1 * sigma) / (2 * sqrt_T)
                     + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365

        gamma = n_d1 / (S * sigma * sqrt_T)
        vega = S * n_d1 * sqrt_T / 100

        return Greeks(delta=round(delta, 6), gamma=round(gamma, 6),
                      theta=round(theta, 6), vega=round(vega, 6), rho=round(rho, 6))

    def _bs_price(self, S, K, T, r, sigma, option_type):
        if T <= 0 or sigma <= 0:
            return max(S - K, 0) if option_type == "call" else max(K - S, 0)
        d1, d2 = self._d1_d2(S, K, T, r, sigma)
        if option_type == "call":
            return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    def calculate_iv(self, market_price: float, S: float, K: float, T: float,
                     r: float, option_type: str) -> float:
        if market_price <= 0 or T <= 0:
            return 0.0
        intrinsic = max(S - K, 0) if option_type == "call" else max(K - S, 0)
        if market_price < intrinsic:
            return 0.0
        try:
            # Newton-Raphson
            sigma = 0.3
            for _ in range(100):
                price = self._bs_price(S, K, T, r, sigma, option_type)
                d1, _ = self._d1_d2(S, K, T, r, sigma)
                vega = S * norm.pdf(d1) * math.sqrt(T)
                if abs(vega) < 1e-10:
                    break
                diff = price - market_price
                sigma -= diff / vega
                if sigma <= 0:
                    sigma = 0.001
                if abs(diff) < 1e-6:
                    return round(sigma, 6)
            # Fallback Brent
            return round(brentq(
                lambda s: self._bs_price(S, K, T, r, s, option_type) - market_price,
                0.001, 10.0, xtol=1e-6), 6)
        except Exception:
            return 0.0

    def position_greeks(self, legs: List[OptionLeg]) -> PositionGreeks:
        total = PositionGreeks(delta=0, gamma=0, theta=0, vega=0, rho=0, legs=len(legs))
        for leg in legs:
            g = self.calculate_all_greeks(leg.S, leg.K, leg.T, leg.r,
                                           leg.sigma, leg.option_type)
            mult = leg.qty
            total.delta += g.delta * mult
            total.gamma += g.gamma * mult
            total.theta += g.theta * mult
            total.vega += g.vega * mult
            total.rho += g.rho * mult
        return total
