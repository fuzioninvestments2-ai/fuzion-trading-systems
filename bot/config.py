"""
bot/config.py
=============
Configuración central del bot + PRESETS (conservador / moderado / agresivo).

Es la BASE que usan todos los demás módulos (Regla 1: cimiento primero). No toca
red ni dinero: solo define parámetros y los valida.

Diseño:
  - `TradingConfig` es un dataclass con TODOS los parámetros de la spec.
  - Los presets ajustan de golpe el nivel de riesgo/exigencia.
  - `required_votes` y `min_confidence` se derivan del `stack_method` para que
    coincidan con la especificación (conservative/moderate/aggressive).
"""

from dataclasses import dataclass, field, asdict


# Relación stack_method -> (votos mínimos de indicadores, confianza mínima).
# El PORQUÉ: cuantos más indicadores exijamos que coincidan y más alta la
# confianza, más conservador (menos señales, pero mejor filtradas).
STACK_METHODS = {
    "conservative": {"required_votes": 4, "min_confidence": 0.80},
    "moderate":     {"required_votes": 3, "min_confidence": 0.70},
    "aggressive":   {"required_votes": 2, "min_confidence": 0.60},
}

# Timeframes válidos (en segundos) para construir velas.
TIMEFRAMES = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600}


@dataclass
class TradingConfig:
    # --- Dinero y objetivos de sesión ---
    trade_capital: float = 50.0          # capital a arriesgar por sesión
    target_profit: float = 5.0           # ganancia objetivo por sesión
    max_sessions_per_day: int = 10
    auto_restart: bool = False

    # --- Estrategia ---
    mode: str = "oscillate"              # "oscillate" (rango) | "slide" (tendencia)
    stack_method: str = "moderate"       # conservative | moderate | aggressive
    timeframe: str = "M5"                # M1/M5/M15/M30/H1
    expiry_time: int = 60                # expiración de la opción binaria (seg)

    # --- Riesgo ---
    max_loss_per_session: float = 15.0   # stop de la sesión (3x capital por defecto)
    stop_loss_enabled: bool = True
    max_consecutive_losses: int = 5
    max_drawdown_percent: float = 0.20   # 20%

    # --- Martingale ---
    # NEUTRALIZADO por diseño: Fuzion es de SEÑALES (solo lectura, no coloca
    # órdenes). Doblar tras perder (martingala) funde la cuenta en una racha
    # normal, así que NINGÚN preset la activa y el bot en vivo no la usa. El campo
    # y su TOPE se conservan solo para poder validar el límite en un test (que el
    # doblado nunca sea infinito); requiere opt-in explícito y jamás ejecuta.
    martingale_enabled: bool = False
    martingale_max_steps: int = 4        # tope duro si alguien la activara a mano
    martingale_multiplier: float = 2.0

    # --- Filtro de pago (payout) ---
    min_payout: float = 0.92             # operar solo activos que paguen >= 92%

    # --- Operación ---
    current_asset: str = "EURUSD_otc"
    analysis_interval: float = 2.0       # segundos entre análisis
    demo: bool = True                    # SIEMPRE demo por defecto (seguridad)

    # --- Derivados del stack_method (se rellenan en __post_init__) ---
    required_votes: int = field(default=3, init=False)
    min_confidence: float = field(default=0.70, init=False)

    def __post_init__(self):
        self.validate()
        params = STACK_METHODS[self.stack_method]
        self.required_votes = params["required_votes"]
        self.min_confidence = params["min_confidence"]

    def validate(self):
        """Falla pronto y claro si algún parámetro no tiene sentido."""
        if self.stack_method not in STACK_METHODS:
            raise ValueError(f"stack_method inválido: {self.stack_method}")
        if self.timeframe not in TIMEFRAMES:
            raise ValueError(f"timeframe inválido: {self.timeframe}")
        if self.mode not in ("oscillate", "slide"):
            raise ValueError(f"mode inválido: {self.mode}")
        if self.trade_capital <= 0:
            raise ValueError("trade_capital debe ser > 0")
        if self.target_profit <= 0:
            raise ValueError("target_profit debe ser > 0")
        if not (0 < self.min_payout <= 1):
            raise ValueError("min_payout debe estar en (0, 1]")
        if self.martingale_enabled and self.martingale_max_steps < 1:
            raise ValueError("martingale_max_steps debe ser >= 1 si está activo")

    def timeframe_seconds(self):
        return TIMEFRAMES[self.timeframe]

    def to_dict(self):
        return asdict(self)


# Presets listos para usar. Cada uno ajusta exigencia y riesgo de una vez.
def get_preset(name):
    """
    Devuelve una TradingConfig preconfigurada.

    - conservador: pocas señales, muy filtradas.
    - moderado: equilibrio.
    - agresivo: más señales (más riesgo), PERO sin martingala (ver arriba).

    Ningún preset activa martingala: solo cambia la exigencia de votos/confianza.
    """
    name = name.lower()
    if name == "conservador":
        return TradingConfig(stack_method="conservative", martingale_enabled=False,
                             target_profit=2.0, max_loss_per_session=10.0)
    if name == "moderado":
        return TradingConfig(stack_method="moderate", martingale_enabled=False,
                             target_profit=5.0, max_loss_per_session=15.0)
    if name == "agresivo":
        return TradingConfig(stack_method="aggressive", martingale_enabled=False,
                             target_profit=10.0, max_loss_per_session=20.0)
    raise ValueError(f"preset desconocido: {name} "
                     f"(usa: conservador | moderado | agresivo)")
