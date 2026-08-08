"""Carga de configuración desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv es opcional en tiempo de ejecución
    load_dotenv = None

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _as_bool(value: str) -> bool:
    return value.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class Config:
    """Configuración de la aplicación."""

    app_name: str = "nuevo_proyecto"
    environment: str = "dev"
    log_level: str = "INFO"
    debug: bool = False

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> "Config":
        """Construye la configuración leyendo el entorno (y .env si existe)."""
        if load_dotenv_file and load_dotenv is not None:
            load_dotenv()

        return cls(
            app_name=os.getenv("APP_NAME", cls.app_name),
            environment=os.getenv("ENVIRONMENT", cls.environment),
            log_level=os.getenv("LOG_LEVEL", cls.log_level).upper(),
            debug=_as_bool(os.getenv("DEBUG", "false")),
        )
