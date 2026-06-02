"""Tests de Greeks Calculator."""
import pytest
from options.common.greeks_calculator import GreeksCalculator


def test_call_delta_positive():
    g = GreeksCalculator()
    greeks = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "call")
    assert 0.4 < greeks.delta < 0.65


def test_put_delta_negative():
    g = GreeksCalculator()
    greeks = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "put")
    assert -0.65 < greeks.delta < -0.35


def test_gamma_positive():
    g = GreeksCalculator()
    greeks = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "call")
    assert greeks.gamma > 0


def test_theta_negative():
    g = GreeksCalculator()
    greeks = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "call")
    assert greeks.theta < 0


def test_vega_positive():
    g = GreeksCalculator()
    greeks = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "call")
    assert greeks.vega > 0


def test_put_call_parity():
    g = GreeksCalculator()
    call = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "call")
    put = g.calculate_all_greeks(100, 100, 0.25, 0.05, 0.20, "put")
    assert abs(call.delta - put.delta - 1.0) < 0.01  # Δcall - Δput = 1


def test_iv_solver_roundtrip():
    g = GreeksCalculator()
    S, K, T, r, sigma = 100, 105, 0.25, 0.05, 0.25
    price = g._bs_price(S, K, T, r, sigma, "call")
    recovered = g.calculate_iv(price, S, K, T, r, "call")
    assert abs(recovered - sigma) < 0.005
