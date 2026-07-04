"""
bot/test_reconexion_interna.py
==============================
Valida el REINICIO INTERNO de la conexión (forzar_reconexion) SIN red. El
principio: reiniciar solo la conexión por dentro (no apagar el proceso ni tocar
el otro bot). Al cerrar el socket vivo, run() reconecta solo; aquí comprobamos
que forzar_reconexion cierra el ws actual y lo invalida.
"""

import asyncio

from bot.pocket_client import PocketOptionClient


def _cliente():
    return PocketOptionClient('42["auth",{}]', demo=True)


class _WsFalso:
    """Socket falso: registra si se le pidió cerrar y expone close_code."""
    def __init__(self):
        self.cerrado = False
        self.close_code = None

    async def close(self):
        self.cerrado = True
        self.close_code = 1000            # como un cierre normal


def test_forzar_reconexion_cierra_e_invalida():
    c = _cliente()
    ws = _WsFalso()
    c._ws = ws
    assert c.is_connected                 # socket vivo (close_code None)
    cerro = asyncio.run(c.forzar_reconexion())
    assert cerro is True                  # había socket que cerrar
    assert ws.cerrado is True             # se pidió cerrar (dispara reconexión)
    assert c._ws is None                  # invalidado: no se envía sobre él
    assert not c.is_connected             # ya no cuenta como conectado
    print("OK forzar_reconexion cierra el socket vivo y lo invalida")


def test_forzar_reconexion_sin_socket():
    c = _cliente()
    c._ws = None                          # nada que cerrar
    cerro = asyncio.run(c.forzar_reconexion())
    assert cerro is False                 # no había socket -> False, sin excepción
    print("OK forzar_reconexion sin socket devuelve False (no rompe)")


if __name__ == "__main__":
    test_forzar_reconexion_cierra_e_invalida()
    test_forzar_reconexion_sin_socket()
    print("\nTODOS OK — reinicio interno de la conexión")
