"""Punto de entrada del proyecto."""

from __future__ import annotations

import logging
import sys

if __package__ in (None, ""):
    # Permite `python src/nuevo_proyecto/main.py` sin instalar el paquete.
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nuevo_proyecto.config import Config

logger = logging.getLogger("nuevo_proyecto")


def main() -> int:
    config = Config.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    logger.info("Iniciando %s (entorno=%s)", config.app_name, config.environment)
    if config.debug:
        logger.debug("Modo depuración activo — configuración: %s", config)

    # TODO: implementar la lógica del proyecto aquí.
    logger.info("Sin tareas configuradas todavía.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
