"""
src/main.py
===========
FASE 2: punto de entrada UNICO del sistema (orquesta todo).

PORQUE: el manual pide un `main.py` que orqueste TODO. En vez de reimplementar
el arranque (Regla 1: no duplicar), este entry-point limpio:
  1. Carga el .env (tokens, SSID) de forma temprana.
  2. Resuelve el PERFIL a lanzar (OTC o REAL) desde CLI o entorno.
  3. Valida que el token del bot exista ANTES de arrancar (falla claro y pronto).
  4. Delega en el orquestador real `bot.telegram_signals.run`, que ya cablea
     Telegram + PocketService + colector + motor.

Cada perfil es un bot AISLADO (su token, su SSID, su base de datos), por eso el
arranque es por-perfil y no "todo a la vez": levantar dos requiere dos procesos
(dos contenedores en compose), no un solo proceso multiplexado.

Uso:
    python -m src.main            # perfil OTC (por defecto)
    python -m src.main REAL       # perfil REAL
    FUZION_PROFILE=REAL python -m src.main
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Perfiles soportados (deben existir en bot.profiles).
PERFILES_VALIDOS = ("OTC", "REAL")


def _cargar_env() -> None:
    """Carga .env si python-dotenv esta disponible. No es fatal si falta."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        # Sin dotenv se usan las variables de entorno del proceso (p. ej. las
        # que inyecta docker-compose); no es un error.
        pass


def resolver_perfil(argv: Optional[list] = None) -> str:
    """
    Determina el perfil: 1er argumento CLI > FUZION_PROFILE > 'OTC'.
    Normaliza a mayusculas y valida contra PERFILES_VALIDOS.
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        perfil = argv[0]
    else:
        perfil = os.getenv("FUZION_PROFILE", "OTC")

    perfil = perfil.strip().upper()
    if perfil not in PERFILES_VALIDOS:
        raise SystemExit(
            f"Perfil invalido: {perfil!r}. Validos: {', '.join(PERFILES_VALIDOS)}")
    return perfil


def _validar_token(perfil: str) -> None:
    """
    Verifica que exista el token del bot ANTES de arrancar, con el mismo criterio
    que `run()` (token propio del perfil, con fallback legacy solo para OTC). Asi
    el fallo es inmediato y con mensaje util, no a mitad del arranque.
    """
    token = os.getenv(f"TELEGRAM_BOT_TOKEN_{perfil}", "").strip()
    if not token and perfil == "OTC":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            f"Falta TELEGRAM_BOT_TOKEN_{perfil} en el entorno/.env. "
            f"Crea el bot con @BotFather y exporta su token.")


def main(argv: Optional[list] = None) -> None:
    """Orquesta el arranque del bot del perfil resuelto."""
    _cargar_env()
    perfil = resolver_perfil(argv)
    _validar_token(perfil)

    # Import tardio: telegram_signals arrastra dependencias pesadas (telegram,
    # pandas...). Importar aqui permite que resolver_perfil/_validar_token se
    # prueben sin cargar todo el stack.
    from bot.telegram_signals import run
    run(perfil)


if __name__ == "__main__":
    main()
