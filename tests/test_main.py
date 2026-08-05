"""
tests/test_main.py
==================
Valida la logica de arranque de `src/main.py` (resolucion de perfil y
validacion de token). SIN red: NO llama a main()/run() (eso levanta Telegram).
"""

from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from src import main   # noqa: E402


def _limpiar_env() -> None:
    for k in ("FUZION_PROFILE", "TELEGRAM_BOT_TOKEN",
              "TELEGRAM_BOT_TOKEN_OTC", "TELEGRAM_BOT_TOKEN_REAL"):
        os.environ.pop(k, None)


def test_resolver_perfil_default_y_cli() -> None:
    _limpiar_env()
    assert main.resolver_perfil([]) == "OTC"          # default
    assert main.resolver_perfil(["real"]) == "REAL"   # normaliza mayusculas
    os.environ["FUZION_PROFILE"] = "real"
    assert main.resolver_perfil([]) == "REAL"         # via entorno
    _limpiar_env()


def test_resolver_perfil_invalido() -> None:
    _limpiar_env()
    try:
        main.resolver_perfil(["XYZ"])
        assert False, "deberia rechazar perfil invalido"
    except SystemExit:
        pass


def test_validar_token() -> None:
    _limpiar_env()
    # Sin token -> corta.
    try:
        main._validar_token("OTC")
        assert False, "deberia fallar sin token"
    except SystemExit:
        pass

    # Fallback legacy solo aplica a OTC.
    os.environ["TELEGRAM_BOT_TOKEN"] = "legacy"
    main._validar_token("OTC")                         # no lanza
    try:
        main._validar_token("REAL")
        assert False, "REAL no usa el token legacy"
    except SystemExit:
        pass

    os.environ["TELEGRAM_BOT_TOKEN_REAL"] = "xxx"
    main._validar_token("REAL")                        # ahora si
    _limpiar_env()


def _run_all() -> None:
    tests = [test_resolver_perfil_default_y_cli, test_resolver_perfil_invalido,
             test_validar_token]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
