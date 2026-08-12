"""
core/config.py (fuzion_fx)
==========================
Carga y valida config/bots.yaml. Resuelve ${VAR} (token/canal de Telegram) desde
el entorno / .env.

Cada bot es un proceso independiente que arranca leyendo SU seccion (f1_m1, ...).
Centralizar la carga da un unico punto de parsing y validacion. Sin red.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

import yaml

# Raiz del proyecto = fuzion_fx/ (…/core/config.py -> dirname x2).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ROOT, "config", "bots.yaml")

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _resolver_env(valor: Any) -> Any:
    """Reemplaza ${VAR} por el valor de entorno (recursivo en dict/list/str)."""
    if isinstance(valor, str):
        return _ENV_RE.sub(lambda m: os.getenv(m.group(1), ""), valor)
    if isinstance(valor, dict):
        return {k: _resolver_env(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_resolver_env(v) for v in valor]
    return valor


def load_config(path: str = None) -> Dict[str, Any]:
    """Carga el yaml y resuelve ${ENV}. Intenta cargar .env primero si existe."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        load_dotenv(os.path.join(os.path.dirname(ROOT), ".env"))  # .env del repo raiz
    except Exception:
        pass

    path = path or DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not raw or "bots" not in raw:
        raise ValueError(f"config invalida: falta la clave 'bots' en {path}")
    return _resolver_env(raw)


def bot_ids(path: str = None) -> List[str]:
    """Ids de bot definidos (f1_m1, f2_m2, ...)."""
    return list(load_config(path)["bots"].keys())


def get_bot_config(bot_id: str, path: str = None) -> Dict[str, Any]:
    """
    Config de UN bot + seccion telegram (token/canal resueltos) + db_path
    absoluto. Falla claro si el bot no existe.
    """
    cfg = load_config(path)
    bots = cfg["bots"]
    if bot_id not in bots:
        raise KeyError(f"bot desconocido: {bot_id}. Validos: {', '.join(bots)}")
    bot = dict(bots[bot_id])
    bot["id"] = bot_id
    bot["telegram"] = cfg.get("telegram", {})
    # Filtro de pago: default global (top-level 'payout') salvo que el bot lo pise.
    # El usuario exige emitir solo en activos con pago real >= 72%.
    bot["payout"] = bot.get("payout", cfg.get("payout", {}))
    if "db_path" in bot and not os.path.isabs(bot["db_path"]):
        bot["db_path"] = os.path.join(ROOT, bot["db_path"])
    return bot
