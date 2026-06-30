"""
indicators/stochastic.py
========================
Oscilador Estocástico (%K y %D), con dos modos:

  1. Cálculo VECTORIZADO por lotes (NumPy)   -> históricos / backtesting.
  2. Cálculo en STREAMING tick a tick         -> WebSocket en vivo (OTC).

Diseño (Reglas del proyecto):
  - Regla 1 (Modular): este módulo SOLO calcula el Estocástico. SRP.
  - Regla 2 (Comentarios): se explica el PORQUÉ de la fórmula.
  - SOLID: sin variables globales mutables; el estado vive en la instancia.

------------------------------------------------------------------------------
FUNDAMENTO MATEMÁTICO (el "porqué")
------------------------------------------------------------------------------
El estocástico mide DÓNDE está el precio actual dentro de su rango reciente
[mínimo, máximo] de las últimas `k_period` muestras. Va de 0 a 100:

        %K_raw = 100 * (close - min_n) / (max_n - min_n)

  - cerca de 100 -> el precio está en la parte ALTA de su rango (sobrecompra).
  - cerca de 0   -> el precio está en la parte BAJA de su rango (sobreventa).

¿Por qué normalizar por el rango (max - min)?  Porque convierte el precio en
una posición relativa adimensional: da igual si el activo vale 1.2 o 45.000,
%K siempre dice "qué tan arriba estoy respecto a mi propio rango reciente".

Suavizados (para reducir ruido del feed OTC, que es sintético y nervioso):
        %K = SMA(%K_raw, smooth_k)     (estocástico "lento")
        %D = SMA(%K,     d_period)     (línea de señal)

NOTA OTC: en datos por tick a veces solo hay 'precio' (no high/low/close por
vela). En ese caso usamos el propio precio como close y derivamos min/max del
buffer de precios. Si se dispone de high/low reales, se pueden pasar aparte.
"""

import numpy as np
from collections import deque


def stoch_vectorized(closes, k_period=14, smooth_k=3, d_period=3,
                     highs=None, lows=None):
    """
    Estocástico vectorizado. Devuelve (%K, %D) como dos arrays float64 del
    mismo largo que `closes`; los valores sin datos suficientes son NaN.

    Si `highs`/`lows` no se pasan, se usan los propios `closes` (caso tick OTC).

    Vectorización: usamos sliding_window_view para obtener TODAS las ventanas
    deslizantes de una vez y aplicar min/max sobre el eje de la ventana, sin
    bucles anidados en Python.
    """
    closes = np.asarray(closes, dtype=np.float64)
    highs = closes if highs is None else np.asarray(highs, dtype=np.float64)
    lows = closes if lows is None else np.asarray(lows, dtype=np.float64)

    if k_period <= 0 or smooth_k <= 0 or d_period <= 0:
        raise ValueError("k_period, smooth_k y d_period deben ser > 0")
    if not (closes.ndim == highs.ndim == lows.ndim == 1):
        raise ValueError("closes/highs/lows deben ser arrays 1D")
    if not (closes.size == highs.size == lows.size):
        raise ValueError("closes/highs/lows deben tener el mismo largo")

    n = closes.size
    k_raw = np.full(n, np.nan, dtype=np.float64)
    if n < k_period:
        return k_raw, np.full(n, np.nan, dtype=np.float64)

    # Ventanas deslizantes (vectorizado, sin bucles anidados):
    win_high = np.lib.stride_tricks.sliding_window_view(highs, k_period)
    win_low = np.lib.stride_tricks.sliding_window_view(lows, k_period)
    max_n = win_high.max(axis=1)          # máximo de cada ventana
    min_n = win_low.min(axis=1)           # mínimo de cada ventana
    rng = max_n - min_n

    # %K_raw solo está definido desde el índice (k_period - 1) en adelante.
    valid_close = closes[k_period - 1:]
    # Evitamos división por cero: si rng == 0 (rango plano) el %K es indefinido;
    # por convención lo fijamos en 50 (punto medio neutro) en vez de NaN/inf.
    with np.errstate(divide="ignore", invalid="ignore"):
        k_valid = np.where(rng == 0, 50.0,
                           100.0 * (valid_close - min_n) / rng)
    k_raw[k_period - 1:] = k_valid

    # Suavizados con medias móviles simples (también vectorizables).
    k = _sma_with_nan(k_raw, smooth_k)
    d = _sma_with_nan(k, d_period)
    return k, d


def _sma_with_nan(series, window):
    """
    SMA simple que respeta los NaN iniciales: el resultado es NaN hasta tener
    `window` valores NO-NaN consecutivos. Implementada con convolución (vector).
    """
    series = np.asarray(series, dtype=np.float64)
    n = series.size
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        raise ValueError("window debe ser > 0")

    # Buscamos el primer índice con dato válido (no NaN).
    valid_mask = ~np.isnan(series)
    if not valid_mask.any():
        return out
    first = np.argmax(valid_mask)         # primer True
    valid = series[first:]
    if valid.size < window:
        return out
    # Media móvil por convolución uniforme (vectorizado).
    kernel = np.ones(window, dtype=np.float64) / window
    sma = np.convolve(valid, kernel, mode="valid")
    out[first + window - 1:] = sma
    return out


class Stochastic:
    """
    Estocástico en STREAMING tick a tick.

    Mantiene un BUFFER CIRCULAR de los últimos `k_period` precios (tamaño fijo)
    para calcular min/max del rango, y dos colas (deque) cortas para suavizar
    %K y %D. Pensado para operación 24/7 con memoria constante.

    SRP: solo calcula el estocástico; no sabe de red ni de Telegram.
    """

    def __init__(self, k_period=14, smooth_k=3, d_period=3):
        if k_period <= 0 or smooth_k <= 0 or d_period <= 0:
            raise ValueError("k_period, smooth_k y d_period deben ser > 0")
        self.k_period = int(k_period)
        self.smooth_k = int(smooth_k)
        self.d_period = int(d_period)

        # Buffer circular de precios para el rango [min, max].
        self._buffer = np.zeros(self.k_period, dtype=np.float64)
        self._index = 0
        self._count = 0

        # Colas para los suavizados (longitud acotada -> memoria constante).
        self._k_raw_window = deque(maxlen=self.smooth_k)
        self._k_window = deque(maxlen=self.d_period)

        self._k = None      # %K suavizado actual
        self._d = None      # %D actual

    @property
    def value(self):
        """Devuelve (%K, %D) actuales (pueden ser None si faltan datos)."""
        return self._k, self._d

    def update(self, price):
        """
        Procesa un tick (precio) y devuelve (%K, %D). Mientras no haya datos
        suficientes, los componentes correspondientes son None (honesto).
        """
        price = float(price)

        # 1) Guardar en buffer circular.
        self._buffer[self._index] = price
        self._index = (self._index + 1) % self.k_period
        self._count = min(self._count + 1, self.k_period)

        # 2) Aún no hay `k_period` precios -> no se puede definir el rango.
        if self._count < self.k_period:
            return None, None

        # 3) %K_raw sobre el rango actual del buffer.
        max_n = self._buffer.max()
        min_n = self._buffer.min()
        rng = max_n - min_n
        k_raw = 50.0 if rng == 0 else 100.0 * (price - min_n) / rng

        # 4) Suavizado %K (necesita `smooth_k` valores de %K_raw).
        self._k_raw_window.append(k_raw)
        if len(self._k_raw_window) < self.smooth_k:
            return None, None
        self._k = sum(self._k_raw_window) / self.smooth_k

        # 5) %D = SMA de %K (necesita `d_period` valores de %K).
        self._k_window.append(self._k)
        if len(self._k_window) < self.d_period:
            return self._k, None
        self._d = sum(self._k_window) / self.d_period
        return self._k, self._d

    def recent_prices(self):
        """Precios del buffer en orden cronológico (más antiguo -> reciente)."""
        if self._count < self.k_period:
            return self._buffer[: self._index].copy()
        return np.roll(self._buffer, -self._index).copy()
