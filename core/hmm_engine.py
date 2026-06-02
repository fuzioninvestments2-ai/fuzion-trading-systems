"""
HMM Engine — Gaussian Hidden Markov Model para detección de regímenes de mercado.
SOLO Forward algorithm. NUNCA Viterbi (look-ahead bias).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=DeprecationWarning)


class RegimeLabel(Enum):
    CRASH = "crash"
    BEAR = "bear"
    NEUTRAL = "neutral"
    BULL = "bull"
    EUPHORIA = "euphoria"


@dataclass
class RegimeInfo:
    regime_id: int
    label: RegimeLabel
    expected_return: float
    expected_volatility: float
    position_size_pct: float
    leverage: float
    description: str


@dataclass
class RegimeState:
    current_regime: RegimeInfo
    regime_probability: float
    all_probabilities: np.ndarray
    is_flickering: bool
    is_uncertain: bool
    bars_in_regime: int
    last_change_bar: int


class HMMEngine:
    """
    Gaussian HMM con BIC model selection (3-5 estados, 10 restarts).
    14 features z-scored, rolling z-score 126 días, stability filter 3 barras.
    """

    def __init__(self, config: dict):
        self.n_candidates: List[int] = config.get("n_candidates", [3, 4, 5])
        self.n_init: int = config.get("n_init", 10)
        self.covariance_type: str = config.get("covariance_type", "full")
        self.n_iter: int = config.get("n_iter", 200)
        self.random_state: int = config.get("random_state", 42)
        self.min_train_bars: int = config.get("min_train_bars", 252)
        self.refit_interval: int = config.get("refit_interval", 5)
        self.zscore_window: int = config.get("zscore_window", 126)
        self.stability_bars: int = config.get("stability_bars", 3)
        self.flicker_window: int = config.get("flicker_window", 20)
        self.flicker_threshold: int = config.get("flicker_threshold", 4)

        self.model: Optional[GaussianHMM] = None
        self.n_states: int = 0
        self.regime_map: dict = {}
        self._raw_state_history: List[int] = []
        self._confirmed_state_history: List[int] = []
        self._bars_since_refit: int = 0
        self._scaler = StandardScaler()

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _compute_features(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Calcula las 14 features z-scored para el HMM."""
        df = bars.copy()
        close = df["close"]
        volume = df.get("volume", pd.Series(np.ones(len(df)), index=df.index))

        # Returns
        df["ret_1d"] = close.pct_change(1)
        df["ret_5d"] = close.pct_change(5)
        df["ret_21d"] = close.pct_change(21)

        # Realized volatility
        df["vol_10d"] = df["ret_1d"].rolling(10).std() * np.sqrt(252)
        df["vol_21d"] = df["ret_1d"].rolling(21).std() * np.sqrt(252)

        # Volume ratio
        vol_ma = volume.rolling(21).mean()
        df["volume_ratio"] = volume / vol_ma.replace(0, np.nan)

        # Trend
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        df["trend_ema20"] = (close - ema20) / ema20
        df["trend_ema50"] = (close - ema50) / ema50

        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi14"] = 100 - (100 / (1 + rs))

        # MACD signal
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        df["macd_signal"] = macd.ewm(span=9, adjust=False).mean()

        # Bollinger %b
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20
        df["bollinger_pct_b"] = (close - lower) / (upper - lower).replace(0, np.nan)

        # Stochastic %K
        low14 = df["low"].rolling(14).min() if "low" in df.columns else close.rolling(14).min()
        high14 = df["high"].rolling(14).max() if "high" in df.columns else close.rolling(14).max()
        df["stoch_k"] = (close - low14) / (high14 - low14).replace(0, np.nan)

        # ADX (simplified)
        if "high" in df.columns and "low" in df.columns:
            high = df["high"]
            low = df["low"]
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)
            atr14 = tr.rolling(14).mean()
            dm_plus = (high.diff()).clip(lower=0)
            dm_minus = (-low.diff()).clip(lower=0)
            di_plus = 100 * dm_plus.rolling(14).mean() / atr14.replace(0, np.nan)
            di_minus = 100 * dm_minus.rolling(14).mean() / atr14.replace(0, np.nan)
            dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
            df["adx"] = dx.rolling(14).mean()
        else:
            df["adx"] = 25.0

        feature_cols = [
            "ret_1d", "ret_5d", "ret_21d",
            "vol_10d", "vol_21d",
            "volume_ratio",
            "trend_ema20", "trend_ema50",
            "rsi14", "macd_signal",
            "bollinger_pct_b", "stoch_k",
            "adx",
        ]
        # Añadir vol_ratio_change como feature 14
        df["vol_ratio_change"] = df["vol_10d"] / df["vol_21d"].replace(0, np.nan)
        feature_cols.append("vol_ratio_change")

        return df[feature_cols]

    def _rolling_zscore(self, features: pd.DataFrame) -> pd.DataFrame:
        """Rolling z-score con ventana de zscore_window días."""
        zscored = pd.DataFrame(index=features.index, columns=features.columns, dtype=float)
        for col in features.columns:
            s = features[col]
            roll_mean = s.rolling(self.zscore_window, min_periods=30).mean()
            roll_std = s.rolling(self.zscore_window, min_periods=30).std()
            zscored[col] = (s - roll_mean) / roll_std.replace(0, np.nan)
        return zscored.clip(-5, 5)

    # ------------------------------------------------------------------
    # Model selection via BIC
    # ------------------------------------------------------------------

    def _fit_candidate(self, X: np.ndarray, n: int) -> Tuple[GaussianHMM, float]:
        best_model = None
        best_bic = np.inf
        for seed in range(self.n_init):
            try:
                model = GaussianHMM(
                    n_components=n,
                    covariance_type=self.covariance_type,
                    n_iter=self.n_iter,
                    random_state=self.random_state + seed,
                    verbose=False,
                )
                model.fit(X)
                if model.monitor_.converged:
                    log_likelihood = model.score(X)
                    k = n * n + n * X.shape[1] + n * X.shape[1] * (X.shape[1] + 1) // 2
                    bic = -2 * log_likelihood * len(X) + k * np.log(len(X))
                    if bic < best_bic:
                        best_bic = bic
                        best_model = model
            except Exception:
                continue
        return best_model, best_bic

    def _select_model(self, X: np.ndarray) -> GaussianHMM:
        best_model = None
        best_bic = np.inf
        for n in self.n_candidates:
            model, bic = self._fit_candidate(X, n)
            if model is not None and bic < best_bic:
                best_bic = bic
                best_model = model
        if best_model is None:
            # Fallback
            best_model = GaussianHMM(n_components=3, covariance_type="full",
                                     n_iter=100, random_state=42)
            best_model.fit(X)
        return best_model

    # ------------------------------------------------------------------
    # Regime labeling
    # ------------------------------------------------------------------

    def _label_regimes(self, model: GaussianHMM) -> dict:
        """
        Ordena estados por volatilidad esperada (ascendente) y asigna labels.
        Regímenes: CRASH, BEAR, NEUTRAL, BULL, EUPHORIA
        """
        n = model.n_components
        means = model.means_
        covars = model.covars_

        # Volatilidad = raíz de varianza del feature vol_10d (índice 3)
        vols = []
        for i in range(n):
            if covars.ndim == 3:
                vol_var = covars[i][3][3] if covars[i].shape[0] > 3 else covars[i][0][0]
            else:
                vol_var = covars[i][3] if len(covars[i]) > 3 else covars[i][0]
            vols.append(np.sqrt(abs(vol_var)))

        sorted_states = np.argsort(vols)

        label_sequence = [RegimeLabel.NEUTRAL] * n
        labels_available = [RegimeLabel.CRASH, RegimeLabel.BEAR, RegimeLabel.NEUTRAL,
                            RegimeLabel.BULL, RegimeLabel.EUPHORIA]

        # Distribuir labels según número de estados
        if n == 3:
            assignment = [labels_available[1], labels_available[2], labels_available[4]]
        elif n == 4:
            assignment = [labels_available[1], labels_available[2],
                          labels_available[3], labels_available[4]]
        else:
            assignment = labels_available

        regime_map = {}
        for rank, state_idx in enumerate(sorted_states):
            label = assignment[min(rank, len(assignment) - 1)]
            label_sequence[state_idx] = label

            # Retorno esperado basado en media del feature ret_21d
            expected_return = float(means[state_idx][2]) * 12
            # Vol esperada
            expected_vol = float(vols[state_idx]) * np.sqrt(252)

            # Tamaño de posición y leverage por régimen
            pos_size, lev = self._regime_params(label)

            regime_map[state_idx] = RegimeInfo(
                regime_id=state_idx,
                label=label,
                expected_return=expected_return,
                expected_volatility=expected_vol,
                position_size_pct=pos_size,
                leverage=lev,
                description=self._regime_description(label),
            )

        return regime_map

    @staticmethod
    def _regime_params(label: RegimeLabel) -> Tuple[float, float]:
        params = {
            RegimeLabel.CRASH: (0.0, 1.0),
            RegimeLabel.BEAR: (0.25, 1.0),
            RegimeLabel.NEUTRAL: (0.5, 1.0),
            RegimeLabel.BULL: (0.75, 1.1),
            RegimeLabel.EUPHORIA: (0.5, 1.0),
        }
        return params.get(label, (0.5, 1.0))

    @staticmethod
    def _regime_description(label: RegimeLabel) -> str:
        descriptions = {
            RegimeLabel.CRASH: "Volatilidad extrema, correlaciones colapsan — cash is king",
            RegimeLabel.BEAR: "Tendencia bajista sostenida — reducir exposición",
            RegimeLabel.NEUTRAL: "Mercado lateral, baja volatilidad — estrategias de income",
            RegimeLabel.BULL: "Tendencia alcista — momentum y trend following",
            RegimeLabel.EUPHORIA: "Rally extremo, posible burbuja — reducir riesgo",
        }
        return descriptions.get(label, "Régimen desconocido")

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(self, bars: pd.DataFrame) -> None:
        if len(bars) < self.min_train_bars:
            raise ValueError(f"Se necesitan al menos {self.min_train_bars} barras para entrenar")

        features = self._compute_features(bars)
        zscored = self._rolling_zscore(features)
        X = zscored.dropna().values

        self.model = self._select_model(X)
        self.n_states = self.model.n_components
        self.regime_map = self._label_regimes(self.model)
        self._raw_state_history = []
        self._confirmed_state_history = []
        self._bars_since_refit = 0

    # ------------------------------------------------------------------
    # Prediction — SOLO Forward algorithm
    # ------------------------------------------------------------------

    def predict_regime(self, bars: pd.DataFrame) -> RegimeState:
        """
        Predice el régimen actual usando SOLO el Forward algorithm.
        NUNCA usa Viterbi para evitar look-ahead bias.
        """
        if self.model is None:
            raise RuntimeError("El modelo no ha sido entrenado. Llama a fit() primero.")

        # Refit walk-forward
        self._bars_since_refit += 1
        if self._bars_since_refit >= self.refit_interval and len(bars) >= self.min_train_bars:
            self.fit(bars)
            self._bars_since_refit = 0

        features = self._compute_features(bars)
        zscored = self._rolling_zscore(features)
        X = zscored.dropna().values

        if len(X) < 10:
            raise ValueError("Datos insuficientes para predicción")

        # Forward algorithm: posteriors para el último estado
        log_posteriors = self.model.predict_proba(X)
        current_posteriors = log_posteriors[-1]
        raw_state = int(np.argmax(current_posteriors))

        self._raw_state_history.append(raw_state)

        # Stability filter: requiere stability_bars de persistencia
        confirmed_state = self._apply_stability_filter(raw_state)
        self._confirmed_state_history.append(confirmed_state)

        # Flicker detection
        is_flickering = self._detect_flicker()

        # Incertidumbre si probabilidad < 0.5
        prob = float(current_posteriors[confirmed_state])
        is_uncertain = prob < 0.5 or is_flickering

        bars_in_regime = self._count_bars_in_current_regime()
        last_change = self._last_change_bar()

        regime_info = self.regime_map.get(confirmed_state, list(self.regime_map.values())[0])

        # Si incierto, reducir tamaño y leverage
        if is_uncertain:
            from copy import deepcopy
            regime_info = deepcopy(regime_info)
            regime_info.position_size_pct *= 0.5
            regime_info.leverage = 1.0

        return RegimeState(
            current_regime=regime_info,
            regime_probability=prob,
            all_probabilities=current_posteriors,
            is_flickering=is_flickering,
            is_uncertain=is_uncertain,
            bars_in_regime=bars_in_regime,
            last_change_bar=last_change,
        )

    def _apply_stability_filter(self, raw_state: int) -> int:
        history = self._raw_state_history
        if len(history) < self.stability_bars:
            return raw_state
        # Confirmar si los últimos stability_bars son el mismo estado
        recent = history[-self.stability_bars:]
        if all(s == raw_state for s in recent):
            return raw_state
        # Mantener el último estado confirmado
        if self._confirmed_state_history:
            return self._confirmed_state_history[-1]
        return raw_state

    def _detect_flicker(self) -> bool:
        if len(self._raw_state_history) < self.flicker_window:
            return False
        recent = self._raw_state_history[-self.flicker_window:]
        changes = sum(1 for i in range(1, len(recent)) if recent[i] != recent[i - 1])
        return changes > self.flicker_threshold

    def _count_bars_in_current_regime(self) -> int:
        if not self._confirmed_state_history:
            return 0
        current = self._confirmed_state_history[-1]
        count = 0
        for s in reversed(self._confirmed_state_history):
            if s == current:
                count += 1
            else:
                break
        return count

    def _last_change_bar(self) -> int:
        if len(self._confirmed_state_history) < 2:
            return 0
        current = self._confirmed_state_history[-1]
        for i in range(len(self._confirmed_state_history) - 2, -1, -1):
            if self._confirmed_state_history[i] != current:
                return len(self._confirmed_state_history) - 1 - i
        return len(self._confirmed_state_history)

    def get_regime_info(self) -> List[RegimeInfo]:
        return list(self.regime_map.values())

    def is_trained(self) -> bool:
        return self.model is not None
