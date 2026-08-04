"""
config/settings.py
==================
Configuracion CENTRALIZADA del sistema Fuzion FX (TAREA 1 del manual v2.0).

PORQUE: hoy la configuracion vive dispersa en `bot/config.py` (presets de riesgo)
y `bot/profiles.py` (perfiles OTC/REAL) y `bot/cuantico.py` (timeframes/umbral).
Este modulo la unifica en UNA fuente limpia y tipada. NO se borran los originales
todavia (el manual lo prohibe): esto solo centraliza CONSTANTES y las valida.
No toca red ni dinero.

Los valores se toman TAL CUAL del bot real (no se inventan):
  - 9 timeframes y pesos de grupo -> `bot/cuantico.py` (GRUPOS / TIMEFRAMES_9).
  - Umbral 90%                    -> `bot/cuantico.py` (PROB_MIN / CONV_MIN).
  - Pares forex                   -> `bot/profiles.py` (REAL_MAJORS / OTC_MAJORS).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


# --- Paths de datos -------------------------------------------------------
# PORQUE: rutas absolutas desde la raiz del proyecto para que el bot funcione
# igual sin importar el directorio desde el que se lance.
ROOT_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR: str = os.path.join(ROOT_DIR, "data")
DATASETS_OTC_DIR: str = os.path.join(ROOT_DIR, "datasets", "otc")
DATASETS_REAL_DIR: str = os.path.join(ROOT_DIR, "datasets", "real")
DB_OTC_PATH: str = os.path.join(ROOT_DIR, "history.db")
DB_REAL_PATH: str = os.path.join(ROOT_DIR, "history_real.db")


# --- Pares de forex -------------------------------------------------------
# PORQUE: se copian de `bot/profiles.py` (la fuente real del bot). El manual
# habla de "18 pares"; el menu REAL de Pocket Option lista 22 y el OTC 10. Se
# conservan ambos TAL CUAL: no se recorta ni se inventa ningun par. Si se quiere
# la lista exacta de 18, se define en el checkpoint (no a ciegas).
FOREX_PAIRS_REAL: Tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "GBPJPY", "GBPAUD",
    "GBPCAD", "GBPCHF", "AUDJPY", "AUDCAD", "AUDNZD", "CADJPY", "CHFJPY",
    "NZDJPY",
)
FOREX_PAIRS_OTC: Tuple[str, ...] = (
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
    "AUDCAD_otc", "EURJPY_otc", "GBPJPY_otc", "EURGBP_otc", "USDCHF_otc",
)


# --- Pesos de grupo -------------------------------------------------------
# PORQUE: el motor pondera por GRUPO de timeframes, no por timeframe suelto. Los
# nombres del manual (scalping/intraday/swing) mapean 1:1 con los grupos internos
# del motor (ultra/corto/medio en bot/cuantico.py). MISMOS pesos: 15/50/35%.
#   scalping  <- ultra  (5s, 10s, 15s)      -> 15%
#   intraday  <- corto  (1m, 2m, 3m, 5m)    -> 50%
#   swing     <- medio  (10m, 15m)          -> 35%
GROUP_WEIGHTS: Dict[str, float] = {
    "scalping": 0.15,
    "intraday": 0.50,
    "swing": 0.35,
}


# --- Timeframes del bot ---------------------------------------------------
# PORQUE: cada uno de los 9 tiempos necesita su grupo (para el peso) y una
# expiracion sugerida de la opcion binaria. `expiry_minutes` = duracion del
# timeframe en minutos, con minimo 1 (Pocket Option no vende expiraciones < 1m).
# SUPUESTO a validar en checkpoint: expiry = el propio timeframe; si prefieres
# otra regla (p.ej. expiry fijo de 1m), se ajusta aqui.
@dataclass(frozen=True)
class Timeframe:
    seconds: int
    label: str            # etiqueta legible: "5s", "1m", "15m"...
    group: str            # "scalping" | "intraday" | "swing"
    expiry_minutes: int   # expiracion sugerida de la opcion binaria

    @property
    def weight(self) -> float:
        """Peso individual = peso del grupo / nº de timeframes del grupo."""
        n = sum(1 for t in BOT_TIMEFRAMES if t.group == self.group)
        return GROUP_WEIGHTS[self.group] / n


BOT_TIMEFRAMES: Tuple[Timeframe, ...] = (
    Timeframe(5, "5s", "scalping", 1),
    Timeframe(10, "10s", "scalping", 1),
    Timeframe(15, "15s", "scalping", 1),
    Timeframe(60, "1m", "intraday", 1),
    Timeframe(120, "2m", "intraday", 2),
    Timeframe(180, "3m", "intraday", 3),
    Timeframe(300, "5m", "intraday", 5),
    Timeframe(600, "10m", "swing", 10),
    Timeframe(900, "15m", "swing", 15),
)


# --- Umbral de decision ---------------------------------------------------
# PORQUE: el Motor Cuantico solo marca OPERAR si Probabilidad >= 90 Y
# Convergencia >= 90 (bot/cuantico.py PROB_MIN / CONV_MIN). Umbral duro: menos
# senales, mejor filtradas. No se garantiza acierto; es disciplina.
PROB_MIN: float = 90.0
CONV_MIN: float = 90.0


def get_timeframe(seconds: int) -> Optional[Timeframe]:
    """Devuelve el Timeframe por sus segundos, o None si no esta en la escala."""
    for tf in BOT_TIMEFRAMES:
        if tf.seconds == seconds:
            return tf
    return None


def validate_settings() -> None:
    """Falla pronto y claro si la configuracion es incoherente (robustez)."""
    total = sum(GROUP_WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"Los pesos de grupo deben sumar 1.0 (suman {total})")
    if len(BOT_TIMEFRAMES) != 9:
        raise ValueError(f"Se esperaban 9 timeframes, hay {len(BOT_TIMEFRAMES)}")
    for tf in BOT_TIMEFRAMES:
        if tf.group not in GROUP_WEIGHTS:
            raise ValueError(f"grupo invalido en {tf.label}: {tf.group}")
        if tf.expiry_minutes < 1:
            raise ValueError(f"expiry_minutes debe ser >= 1 ({tf.label})")
    if not (0 < PROB_MIN <= 100) or not (0 < CONV_MIN <= 100):
        raise ValueError("PROB_MIN y CONV_MIN deben estar en (0, 100]")


# Se valida al importar: si algo esta mal, el bot no arranca con datos corruptos.
validate_settings()
