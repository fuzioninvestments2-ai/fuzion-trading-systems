"""
scripts/autotest.py (fuzion_fx)
===============================
COMANDO de auto-verificacion: corre TODA la bateria de tests (sin red) y muestra
un resumen simple PASA/FALLA. Sirve para confirmar, despues de cada actualizacion,
que el bot esta sano antes de la sesion. No toca datos ni conexiones.

    python fuzion_fx/scripts/autotest.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_AQUI)                       # fuzion_fx/
TESTS_DIR = os.path.join(ROOT, "tests")


def main() -> int:
    tests = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    if not tests:
        print("No hay tests en", TESTS_DIR)
        return 1
    print(f"Auto-verificacion Fuzion FX: {len(tests)} archivos de prueba\n")
    ok = 0
    fallos = []
    for t in tests:
        nombre = os.path.basename(t)
        r = subprocess.run([sys.executable, t], capture_output=True, text=True,
                           cwd=ROOT)
        if r.returncode == 0:
            ok += 1
            print(f"  OK    {nombre}")
        else:
            fallos.append(nombre)
            # Ultima linea util del error (para diagnostico rapido).
            err = (r.stderr or r.stdout or "").strip().splitlines()
            detalle = err[-1] if err else "sin detalle"
            print(f"  FALLA {nombre}  -> {detalle}")

    print(f"\nResultado: {ok}/{len(tests)} OK", end="")
    if fallos:
        print(f"  ·  FALLARON: {', '.join(fallos)}")
        print("El bot tiene un problema en el codigo. Pasale esta lista a Claude.")
        return 1
    print("\nTodo sano. El bot esta listo para operar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
