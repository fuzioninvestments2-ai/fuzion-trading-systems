"""
bot/test_cloud_push.py
======================
Valida la subida robusta (reintento pull+push) SIN git real: se inyecta un runner
falso que simula rechazos "fetch first" y luego un push exitoso.
"""

from bot.cloud_push import subir


class _GitFalso:
    """
    Runner de comandos git simulado. `push_falla_veces` pushes se rechazan con
    'fetch first' antes de aceptar. Registra los comandos ejecutados.
    """
    def __init__(self, push_falla_veces=0, add_rc=0, hay_cambios=True):
        self.push_falla_veces = push_falla_veces
        self.add_rc = add_rc
        self.hay_cambios = hay_cambios
        self.comandos = []
        self.pushes = 0
        self.pulls = 0

    def __call__(self, cmd, timeout=300):
        self.comandos.append(cmd)
        sub = cmd[1]
        if sub == "add":
            return self.add_rc, ""
        if sub == "commit":
            return (0, "1 file changed") if self.hay_cambios else (1, "nothing to commit")
        if sub == "pull":
            self.pulls += 1
            return 0, "Already up to date."
        if sub == "push":
            self.pushes += 1
            if self.pushes <= self.push_falla_veces:
                return 1, "! [rejected] (fetch first)\nerror: failed to push"
            return 0, "abc..def  main -> main"
        return 0, ""


def test_push_a_la_primera():
    git = _GitFalso(push_falla_veces=0)
    ok = subir(runner=git)
    assert ok is True
    assert git.pushes == 1 and git.pulls == 1
    print("OK sube al primer intento (pull+push)")


def test_reintenta_hasta_entrar():
    # Los 2 primeros push se rechazan; el 3º entra. Debe reintentar y lograrlo.
    git = _GitFalso(push_falla_veces=2)
    ok = subir(runner=git, intentos=6)
    assert ok is True
    assert git.pushes == 3
    assert git.pulls == 3                       # un pull antes de cada push
    print(f"OK reintenta y sube al 3er intento ({git.pushes} pushes)")


def test_agota_intentos_no_rompe():
    # El push SIEMPRE se rechaza: devuelve False sin lanzar excepción.
    git = _GitFalso(push_falla_veces=99)
    ok = subir(runner=git, intentos=4)
    assert ok is False
    assert git.pushes == 4                       # respetó el tope de intentos
    print("OK agota intentos y devuelve False (no rompe el proceso)")


def test_add_falla_no_sube():
    git = _GitFalso(add_rc=1)
    ok = subir(runner=git)
    assert ok is False
    assert git.pushes == 0                        # ni intenta push si add falló
    print("OK si 'git add' falla, no intenta subir")


def test_sin_cambios_igual_sube_commits_previos():
    # 'commit' sin cambios (rc!=0) NO aborta: puede haber commits locales que subir.
    git = _GitFalso(push_falla_veces=0, hay_cambios=False)
    ok = subir(runner=git)
    assert ok is True and git.pushes == 1
    print("OK sin cambios locales igual empuja (por commits previos)")


if __name__ == "__main__":
    test_push_a_la_primera()
    test_reintenta_hasta_entrar()
    test_agota_intentos_no_rompe()
    test_add_falla_no_sube()
    test_sin_cambios_igual_sube_commits_previos()
    print("\nTODOS OK — subida robusta a la nube")
