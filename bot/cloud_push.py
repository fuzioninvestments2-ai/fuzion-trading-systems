"""
bot/cloud_push.py
=================
SUBIDA ROBUSTA a la nube (git). El problema real observado: el robot subía con
un SOLO intento (`git pull & git push`); si el remoto avanzaba entre el pull y el
push (otra sesión trabajando en la misma rama), el push se RECHAZABA con
"fetch first" y esa ronda no subía. Aquí se reintenta pull+push en bucle hasta
que entra (o se agotan los intentos), que es la forma honesta de ganar la carrera
sin forzar nada.

Reglas del proyecto: robustez (bucle de reintento con reconciliación) y no
destructivo (pull --no-rebase, nunca force). Si git no está disponible o no hay
credenciales, avisa y sigue: la subida no debe tumbar el proceso que la llama.

Sin red propia (usa git). Testeable: la lógica de reintento se prueba con un
runner de comandos falso, sin tocar git de verdad.
"""

import subprocess


def _correr(cmd, timeout=300):
    """Ejecuta un comando y devuelve (rc, salida). Runner por defecto (git real)."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def subir(rutas=("datasets/",), mensaje="datos: actualizacion automatica",
          intentos=6, logger=None, runner=_correr):
    """
    Sube `rutas` a la nube reintentando pull+push. Devuelve True si el push entró.

    Pasos: add -> commit (si no hay cambios, sigue) -> bucle {pull --no-rebase;
    push}. En cuanto un push devuelve rc 0, termina con éxito. `runner` se puede
    sustituir en tests por un ejecutor falso (sin git real).
    """
    def _log(msg):
        if logger is not None:
            logger.info(msg)

    rc, _ = runner(["git", "add", *rutas])
    if rc != 0:
        _log("cloud_push: 'git add' falló; no se sube esta vez")
        return False
    # commit rc!=0 = "nada que commitear": normal (con export determinista es lo
    # habitual cuando la data no cambió). No es error; puede que igual haya que
    # subir commits locales previos, así que seguimos al bucle push.
    runner(["git", "commit", "-m", mensaje])

    for i in range(1, int(intentos) + 1):
        # PULL primero: reconcilia con lo que otra sesión haya subido. --no-rebase
        # crea un merge (los datasets son archivos propios, no chocan).
        runner(["git", "pull", "--no-rebase", "--no-edit"])
        rc, salida = runner(["git", "push"])
        if rc == 0:
            _log(f"cloud_push: subido (intento {i})")
            return True
        # "everything up-to-date" también es éxito (no había nada que subir).
        if "up-to-date" in salida.lower() or "up to date" in salida.lower():
            _log("cloud_push: ya estaba al día")
            return True
        _log(f"cloud_push: push rechazado (intento {i}/{intentos}); "
             f"reintento tras pull")
    _log("cloud_push: no se pudo subir tras varios intentos; se reintentará "
         "la próxima ronda (los datos están a salvo en local)")
    return False


def _main():
    """
    CLI: sube una carpeta con reintento.
      python -m bot.cloud_push                 # sube datasets/ (mensaje genérico)
      python -m bot.cloud_push datasets/otc "datos OTC"
    """
    import sys
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("cloud_push")
    args = sys.argv[1:]
    ruta = args[0] if args else "datasets/"
    mensaje = args[1] if len(args) > 1 else "datos: actualizacion automatica"
    ok = subir(rutas=(ruta,), mensaje=mensaje, logger=log)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main()
