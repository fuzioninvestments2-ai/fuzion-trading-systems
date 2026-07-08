"""
bot/skills/base_skill.py
========================
Clase base de todos los skills. Un skill recibe el contexto de mercado y devuelve
un VOTO: dirección (CALL/PUT/NEUTRAL), confianza (0-1) y el porqué.

El contrato de datos (`market_data`) es un dict:
  {
    "df": DataFrame OHLC (columnas open, high, low, close[, volume]) hasta AHORA,
    "pair": "EURUSD", "timeframe": 300  # segundos
  }
Se usa el DataFrame del propio proyecto (no se reinventan las velas).
"""
from abc import ABC, abstractmethod

NEUTRAL = "NEUTRAL"
CALL = "CALL"
PUT = "PUT"


def voto(direccion=NEUTRAL, confianza=0.0, fuerza=0.0, motivo="", extra=None):
    """Estructura estándar del voto de un skill (para no repetir el dict)."""
    return {"direction": direccion, "confidence": float(confianza),
            "signal_strength": float(fuerza), "reason": motivo,
            "indicators_used": extra or {}}


class BaseSkill(ABC):
    """
    Base común. Cada skill implementa `analyze(market_data) -> voto(...)`.
    Lleva su propio historial de aciertos para auto-medirse (aprendizaje).
    """

    def __init__(self, nombre, version="1.0"):
        self.name = nombre
        self.version = version
        self.predictions = 0
        self.correct = 0

    @abstractmethod
    def analyze(self, market_data):
        """Devuelve un voto (usar el helper `voto(...)`)."""
        raise NotImplementedError

    def accuracy(self):
        """Acierto histórico propio (0.5 sin historial = neutro)."""
        return self.correct / self.predictions if self.predictions else 0.5

    def update_performance(self, acerto):
        self.predictions += 1
        if acerto:
            self.correct += 1

    def learn(self, outcome):
        """Aprendizaje en línea opcional; por defecto solo lleva la cuenta."""
        real = outcome.get("real_direction")
        mi = outcome.get("vote")
        if real in (CALL, PUT) and mi in (CALL, PUT):
            self.update_performance(mi == real)

    def metadata(self):
        return {"name": self.name, "version": self.version,
                "accuracy": round(self.accuracy(), 4), "predictions": self.predictions,
                "type": self.__class__.__name__}
