"""
indicators/rsi.py
=================
Relative Strength Index (RSI) de Wilder, con dos modos:

  1. Cálculo VECTORIZADO por lotes (NumPy)   -> históricos / backtesting.
  2. Cálculo en STREAMING tick a tick (O(1))  -> WebSocket en vivo.

Diseño (Reglas del proyecto):
  - Regla 1 (Modular): este módulo SOLO calcula RSI. Responsabilidad única.
  - Regla 2 (Comentarios): se explica el PORQUÉ de la fórmula.
  - SOLID/SRP: sin variables globales mutables; el estado vive en la instancia.

------------------------------------------------------------------------------
FUNDAMENTO MATEMÁTICO (el "porqué")
------------------------------------------------------------------------------
El RSI mide la fuerza relativa entre subidas y bajadas recientes, en [0, 100]:

        RS  = media_suavizada(ganancias) / media_suavizada(perdidas)
        RSI = 100 - 100 / (1 + RS)

donde, para cada paso, respecto al precio anterior:
        ganancia = max(precio_t - precio_(t-1), 0)
        perdida  = max(precio_(t-1) - precio_t, 0)   (valor positivo)

Suavizado de Wilder (no un promedio simple):
        avg_t = (avg_(t-1) * (period - 1) + valor_t) / period
equivalente a una media exponencial con alpha = 1/period.

¿Por qué Wilder y no un promedio simple de ventana?  Porque el promedio simple
hace SALTAR el RSI cuando un valor grande entra o sale de la ventana (efecto
"drop-off"). El suavizado de Wilder reparte el peso de forma decreciente y
continua, dando un RSI más estable y sin saltos artificiales.

Convención de bordes:
  - perdida media == 0  -> RSI = 100 (solo ha subido).
  - ganancia media == 0 -> RSI = 0   (solo ha bajado).
"""

import numpy as np


def rsi_vectorized(prices, period=14):
    """
    RSI de Wilder vectorizado para una serie de precios (orden cronológico).

    Parámetros
    ----------
    prices : array-like 1D de floats
    period : int (>0), por defecto 14 (valor clásico de Wilder)

    Devuelve
    --------
    np.ndarray 1D float64 del mismo largo que `prices`. Los primeros `period`
    valores son NaN porque aún no hay suficientes datos para un RSI fiable
    (es honesto marcarlos como "no disponible" en vez de inventar un número).
    """
    prices = np.asarray(prices, dtype=np.float64)

    if period <= 0:
        raise ValueError("period debe ser un entero > 0")
    if prices.ndim != 1:
        raise ValueError("prices debe ser un array 1D")

    n = prices.size
    rsi = np.full(n, np.nan, dtype=np.float64)
    if n <= period:
        # No hay datos suficientes para una primera media de `period` cambios.
        return rsi

    # Cambios precio a precio (delta_t = precio_t - precio_(t-1)).
    deltas = np.diff(prices)                 # tamaño n-1, vectorizado
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Semilla de Wilder: promedio SIMPLE de las primeras `period` muestras.
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # Primer RSI disponible en el índice `period`.
    rsi[period] = _rs_to_rsi(avg_gain, avg_loss)

    # A partir de ahí, suavizado de Wilder recursivo. Es O(n): una sola pasada,
    # sin bucles anidados. (La recursividad de Wilder no es paralelizable como
    # la EMA, pero un único bucle lineal sigue siendo barato y claro.)
    for i in range(period + 1, n):
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        rsi[i] = _rs_to_rsi(avg_gain, avg_loss)

    return rsi


def _rs_to_rsi(avg_gain, avg_loss):
    """Convierte medias de ganancia/pérdida en RSI, con bordes seguros."""
    if avg_loss == 0.0:
        # Solo subidas -> fuerza compradora máxima.
        return 100.0
    if avg_gain == 0.0:
        # Solo bajadas -> fuerza compradora nula.
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class RSI:
    """
    RSI en STREAMING para procesar ticks uno a uno en O(1).

    Mantiene un BUFFER CIRCULAR de los últimos `period` precios (tamaño fijo,
    sin reasignar memoria) para operación 24/7 con RAM y latencia constantes.

    SRP: solo calcula/actualiza el RSI; no sabe de red ni de Telegram.
    """

    def __init__(self, period=14):
        if period <= 0:
            raise ValueError("period debe ser un entero > 0")
        self.period = int(period)

        self._prev_price = None      # último precio visto (para el delta)
        self._avg_gain = None        # media suavizada de ganancias (Wilder)
        self._avg_loss = None        # media suavizada de pérdidas
        self._seed_gains = []        # acumulador para la semilla inicial
        self._seed_losses = []
        self._rsi = None             # None hasta tener `period` cambios

        # Buffer circular pre-asignado.
        self._buffer = np.zeros(self.period, dtype=np.float64)
        self._index = 0
        self._count = 0

    @property
    def value(self):
        """Último RSI (None mientras no haya datos suficientes)."""
        return self._rsi

    def update(self, price):
        """
        Procesa un nuevo precio (tick) y devuelve el RSI actual (o None si aún
        no hay suficientes datos para un valor fiable).
        """
        price = float(price)

        # 1) Buffer circular (sobrescribe el más antiguo).
        self._buffer[self._index] = price
        self._index = (self._index + 1) % self.period
        self._count = min(self._count + 1, self.period)

        # 2) Primer precio: no hay delta todavía, solo guardamos referencia.
        if self._prev_price is None:
            self._prev_price = price
            return self._rsi

        # 3) Calcular ganancia/pérdida de este paso.
        delta = price - self._prev_price
        self._prev_price = price
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0

        # 4) Fase de SEMILLA: acumulamos los primeros `period` cambios para el
        #    promedio simple inicial de Wilder.
        if self._avg_gain is None:
            self._seed_gains.append(gain)
            self._seed_losses.append(loss)
            if len(self._seed_gains) == self.period:
                self._avg_gain = sum(self._seed_gains) / self.period
                self._avg_loss = sum(self._seed_losses) / self.period
                self._rsi = _rs_to_rsi(self._avg_gain, self._avg_loss)
            return self._rsi

        # 5) Fase de SUAVIZADO de Wilder (recursivo, O(1)).
        self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
        self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period
        self._rsi = _rs_to_rsi(self._avg_gain, self._avg_loss)
        return self._rsi

    def recent_prices(self):
        """Precios del buffer en orden cronológico (más antiguo -> reciente)."""
        if self._count < self.period:
            return self._buffer[: self._index].copy()
        return np.roll(self._buffer, -self._index).copy()
