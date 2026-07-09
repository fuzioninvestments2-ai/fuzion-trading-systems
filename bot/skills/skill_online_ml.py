"""
bot/skills/skill_online_ml.py
=============================
Skill que APRENDE en tiempo real con regresión logística por descenso de gradiente
(SGD), en numpy puro (sin sklearn). Extrae 8 features del mercado, predice
probabilidad de subida y aprende del resultado REAL del precio tras cada operación.

Honestidad de diseño (mismas reglas que el resto):
  - El objetivo (target) es el MOVIMIENTO REAL del precio, NO la dirección que
    eligió el bot. Así aprende a predecir el mercado, no a copiarse.
  - Solo emite señal; nunca coloca órdenes.

Estabilidad numérica: las features se estandarizan con media/desv incrementales
(running) y se recortan a [-5, 5] para que el SGD no explote.
"""
import numpy as np

from bot.skills.base_skill import BaseSkill, voto, CALL, PUT, NEUTRAL

N_FEATURES = 8
MIN_VELAS = 25


class SkillOnlineML(BaseSkill):
    def __init__(self, learning_rate=0.01):
        super().__init__("OnlineML", "1.0")
        self.weights = np.zeros(N_FEATURES)
        self.bias = 0.0
        self.lr = learning_rate
        # Estandarización incremental (media/varianza corridas por feature).
        self._mean = np.zeros(N_FEATURES)
        self._var = np.ones(N_FEATURES)
        self._n = 0
        self._last_features = None          # features del último analyze (para learn)
        self.entrenado_min = 30             # nº de updates antes de confiar

    # --- features ---
    def _features(self, df):
        c = df["close"].astype(float).to_numpy()
        if len(c) < MIN_VELAS:
            return None
        ret = np.diff(np.log(c[-21:]))                       # log-retornos (<=20)
        f = np.zeros(N_FEATURES)
        f[0] = ret[-1]                                        # último retorno
        f[1] = ret[-5:].sum()                                # impulso 5 velas
        f[2] = ret[-20:].std()                               # volatilidad
        f[3] = self._autocorr(ret[-10:])                     # memoria (reversión)
        h = df["high"].astype(float).to_numpy()
        l = df["low"].astype(float).to_numpy()
        rng = (h[-1] - l[-1]) / c[-1] if c[-1] else 0.0
        f[4] = rng                                           # rango relativo
        if "volume" in df.columns and len(df) >= 20:
            v = df["volume"].astype(float).to_numpy()
            avg = v[-20:].mean()
            f[5] = (v[-1] / avg) if avg else 1.0             # volumen relativo
        else:
            f[5] = 1.0
        lo, hi = l[-20:].min(), h[-20:].max()
        f[6] = ((c[-1] - lo) / (hi - lo)) if hi > lo else 0.5  # posición en el rango
        f[7] = ret[-3:].mean() - ret[-10:-3].mean() if len(ret) >= 10 else 0.0  # momentum
        return f

    @staticmethod
    def _autocorr(ret, lag=1):
        if len(ret) <= lag or ret.std() == 0:
            return 0.0
        a, b = ret[:-lag], ret[lag:]
        if a.std() == 0 or b.std() == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    def _estandarizar(self, f):
        """Z-score con media/desv corridas; recorta a [-5,5]."""
        self._n += 1
        d = f - self._mean
        self._mean += d / self._n
        self._var += d * (f - self._mean)                    # Welford
        std = np.sqrt(self._var / self._n) if self._n > 1 else np.ones(N_FEATURES)
        std[std == 0] = 1.0
        z = (f - self._mean) / std
        return np.clip(z, -5, 5)

    # --- predicción ---
    def analyze(self, market_data):
        df = market_data.get("df")
        if df is None or len(df) < MIN_VELAS:
            return voto(NEUTRAL, 0, 0, "datos insuficientes")
        f = self._features(df)
        if f is None:
            return voto(NEUTRAL, 0, 0, "features no disponibles")
        z = self._estandarizar(f)
        self._last_features = z
        p = 1.0 / (1.0 + np.exp(-(np.dot(z, self.weights) + self.bias)))  # sigmoide
        if self.predictions < self.entrenado_min:
            return voto(NEUTRAL, 0, 0, f"entrenando ({self.predictions}/{self.entrenado_min})")
        direccion = CALL if p >= 0.5 else PUT
        conf = abs(p - 0.5) * 2                              # 0 en 0.5, 1 en 0/1
        return voto(direccion, min(conf, 0.9), conf,
                    f"ML p(sube)={p:.2f}", {"prob": round(float(p), 3)})

    # --- aprendizaje ---
    def learn(self, outcome):
        """SGD con el resultado REAL. `outcome`: {real_direction: CALL/PUT}."""
        real = outcome.get("real_direction")
        if self._last_features is None or real not in (CALL, PUT):
            return
        z = self._last_features
        y = 1.0 if real == CALL else 0.0                     # target = mercado real
        p = 1.0 / (1.0 + np.exp(-(np.dot(z, self.weights) + self.bias)))
        error = p - y                                        # gradiente de log-loss
        self.weights -= self.lr * error * z
        self.bias -= self.lr * error
        self.update_performance((p >= 0.5) == (y == 1.0))
        self._last_features = None
