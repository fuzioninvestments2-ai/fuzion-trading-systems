"""Tests del HMM Engine."""
import numpy as np
import pandas as pd
import pytest
from core.hmm_engine import HMMEngine, RegimeLabel


def _make_bars(n: int = 500) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 * np.cumprod(1 + np.random.randn(n) * 0.01)
    high = close * (1 + abs(np.random.randn(n) * 0.005))
    low = close * (1 - abs(np.random.randn(n) * 0.005))
    volume = np.random.randint(1_000_000, 5_000_000, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                          "close": close, "volume": volume}, index=idx)


def test_hmm_trains():
    bars = _make_bars(300)
    hmm = HMMEngine({"n_candidates": [3], "n_init": 2, "min_train_bars": 252, "n_iter": 50})
    hmm.fit(bars)
    assert hmm.is_trained()
    assert hmm.n_states in [3, 4, 5]


def test_hmm_predict_returns_valid_regime():
    bars = _make_bars(400)
    hmm = HMMEngine({"n_candidates": [3], "n_init": 2, "min_train_bars": 252, "n_iter": 50})
    hmm.fit(bars)
    state = hmm.predict_regime(bars)
    assert state.current_regime.label in RegimeLabel
    assert 0.0 <= state.regime_probability <= 1.0


def test_hmm_no_viterbi():
    """El HMM NUNCA debe usar Viterbi — verificar que usa Forward algorithm."""
    bars = _make_bars(400)
    hmm = HMMEngine({"n_candidates": [3], "n_init": 2, "min_train_bars": 252, "n_iter": 50})
    hmm.fit(bars)
    # predict_regime usa predict_proba (Forward), no predict (Viterbi)
    import inspect
    source = inspect.getsource(hmm.predict_regime)
    assert "predict_proba" in source
    assert "viterbi" not in source.lower()


def test_insufficient_data_raises():
    bars = _make_bars(100)
    hmm = HMMEngine({"n_candidates": [3], "n_init": 2, "min_train_bars": 252})
    with pytest.raises(ValueError):
        hmm.fit(bars)


def test_stability_filter():
    bars = _make_bars(400)
    hmm = HMMEngine({"n_candidates": [3], "n_init": 2, "min_train_bars": 252,
                      "n_iter": 50, "stability_bars": 3})
    hmm.fit(bars)
    state = hmm.predict_regime(bars)
    assert state.bars_in_regime >= 0
