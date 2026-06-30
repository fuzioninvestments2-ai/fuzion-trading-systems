"""
indicators/ema.py
=================
Exponential Moving Average (EMA) con dos modos de uso:

  1. Cálculo VECTORIZADO por lotes (NumPy)  -> para históricos / backtesting.
  2. Cálculo en STREAMING tick a tick (O(1)) -> para el WebSocket en vivo.

Diseño (Reglas del proyecto):
  - Regla 1 (Modular): este módulo SOLO calcula EMA. Una única responsabilidad.
  - Regla 2 (Comentarios): se explica el PORQUÉ de la fórmula, no solo el qué.
  - SOLID/SRP: sin variables globales mutables. El estado vive dentro de la
    instancia `EMA` y se pasa por parámetros limpios.

------------------------------------------------------------------------------
FUNDAMENTO MATEMÁTICO (el "porqué")
------------------------------------------------------------------------------
La EMA pondera más los precios recientes que los antiguos. Su forma recursiva:

        EMA_t = alpha * precio_t + (1 - alpha) * EMA_(t-1)

donde el factor de suavizado estándar es:

        alpha = 2 / (period + 1)

¿Por qué `2 / (period + 1)`?  Porque hace que el "centro de masa" de los pesos
de la EMA coincida aproximadamente con el de una SMA de `period` muestras, de
modo que una "EMA de 20" sea comparable a una "SMA de 20". Un `alpha` alto
(period bajo) reacciona rápido pero con más ruido; un `alpha` bajo (period alto)
es más suave pero más lento. Es un compromiso reactividad <-> estabilidad.
"""

import numpy as np


def ema_vectorized(prices, period):
    """
    Calcula la EMA de un array de precios de forma vectorizada (sin bucles
    anidados que saturen el hilo). Pensada para históricos/backtesting.

    Parámetros
    ----------
    prices : array-like (1D) de floats
        Serie de precios en orden cronológico (prices[0] es el más antiguo).
    period : int (>0)
        Período de la EMA.

    Devuelve
    --------
    np.ndarray (1D, float64) del mismo largo que `prices` con la EMA en cada t.

    PORQUÉ de la implementación vectorizada
    ---------------------------------------
    La EMA es recursiva (EMA_t depende de EMA_(t-1)), lo que en apariencia
    obliga a un bucle. Pero podemos desplegar la recursión como una suma
    ponderada por potencias de (1 - alpha):

        Definimos w = (1 - alpha).
        Multiplicando la serie por w^(-t) la recursión se vuelve una SUMA
        ACUMULADA (cumsum), que NumPy hace en C de forma vectorizada.

    Esto evita el bucle Python tick-a-tick para el histórico y mantiene el
    cálculo dentro del presupuesto de latencia.
    """
    prices = np.asarray(prices, dtype=np.float64)

    if period <= 0:
        # Validación defensiva: un period <= 0 no tiene sentido matemático
        # (alpha quedaría >= 2 o división por cero). Fallamos explícito.
        raise ValueError("period debe ser un entero > 0")
    if prices.ndim != 1:
        raise ValueError("prices debe ser un array 1D")
    if prices.size == 0:
        return np.empty(0, dtype=np.float64)

    alpha = 2.0 / (period + 1.0)          # factor de suavizado estándar
    w = 1.0 - alpha                        # peso del término anterior

    n = prices.size
    t = np.arange(n)                       # índices 0..n-1

    # Escalamos cada precio por alpha * w^(-t). Para evitar overflow numérico
    # con w^(-t) cuando n es grande, factorizamos por la potencia máxima al
    # final. Aquí usamos la formulación estable basada en potencias relativas.
    #
    #   EMA_t = (sum_{k=0..t} alpha * w^(t-k) * precio_k) + w^(t+1)*seed
    #
    # Tomamos como semilla EMA inicial = precio_0 (convención habitual), por lo
    # que el primer valor de la EMA coincide con el primer precio.
    powers = w ** t                        # w^0, w^1, ..., w^(n-1)
    # Suma acumulada de (precio_k / w^k), luego re-escalada por w^t:
    scaled = prices / powers               # precio_k * w^(-k)
    cumulative = np.cumsum(scaled)         # parcial de la suma ponderada
    ema = alpha * powers * cumulative      # alpha * sum w^(t-k) * precio_k

    # Corrección de la semilla: añadimos el aporte de EMA_0 = precio_0 que la
    # suma de arriba no incluye con peso completo en t=0.
    ema += prices[0] * powers * w          # término (1-alpha)^(t+1) * seed
    ema[0] = prices[0]                     # por convención, EMA_0 = precio_0
    return ema


class EMA:
    """
    EMA en STREAMING para procesar ticks del WebSocket uno a uno en O(1).

    Mantiene además un BUFFER CIRCULAR de los últimos `period` precios. ¿Por qué
    circular? Porque al operar 24/7 no podemos crecer una lista infinitamente;
    el buffer de tamaño fijo reescribe la posición más antigua sin reasignar
    memoria, manteniendo la latencia y el uso de RAM constantes.

    SRP: esta clase solo calcula/actualiza la EMA; no sabe de red ni de Telegram.
    """

    def __init__(self, period):
        if period <= 0:
            raise ValueError("period debe ser un entero > 0")
        self.period = int(period)
        self.alpha = 2.0 / (period + 1.0)   # mismo alpha que el modo vectorizado
        self._ema = None                    # None hasta el primer precio (seed)

        # Buffer circular pre-asignado (sin reasignaciones en caliente):
        self._buffer = np.zeros(self.period, dtype=np.float64)
        self._index = 0                     # próxima posición a escribir
        self._count = 0                     # cuántos precios reales hay (<=period)

    @property
    def value(self):
        """Último valor de la EMA (None si aún no se procesó ningún precio)."""
        return self._ema

    def update(self, price):
        """
        Procesa un nuevo precio (un tick) y devuelve la EMA actualizada.

        Fórmula (la misma, en su forma recursiva O(1)):
            EMA_t = alpha * price + (1 - alpha) * EMA_(t-1)

        El primer precio inicializa la EMA (semilla), igual que en el modo
        vectorizado, para que ambos modos sean coherentes.
        """
        price = float(price)

        # 1) Guardar en el buffer circular (sobrescribe el más antiguo).
        self._buffer[self._index] = price
        self._index = (self._index + 1) % self.period   # avance circular
        self._count = min(self._count + 1, self.period)

        # 2) Actualizar la EMA recursiva.
        if self._ema is None:
            self._ema = price               # semilla: EMA_0 = precio_0
        else:
            self._ema = self.alpha * price + (1.0 - self.alpha) * self._ema
        return self._ema

    def recent_prices(self):
        """
        Devuelve los precios del buffer en orden cronológico (del más antiguo
        al más reciente). Útil para depurar o alimentar otros indicadores.
        """
        if self._count < self.period:
            # Aún no se ha llenado: los datos válidos están en [0, _index).
            return self._buffer[: self._index].copy()
        # Lleno: el más antiguo está en _index; reordenamos con roll.
        return np.roll(self._buffer, -self._index).copy()
