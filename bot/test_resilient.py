"""
bot/test_resilient.py
=====================
Prueba de validación de la reconexión robusta (Regla 4).

Verifica, SIN red real (inyectando un sleep que no espera):
  (A) ResilientConnector reintenta y acaba conectando tras varios fallos.
  (B) Si se agotan los reintentos (max_retries), lanza ConnectionError.
  (C) El backoff nunca excede max_delay.
  (D) ResilientPocketOptionClient (la subclase) reconecta sin tocar el original,
      y el cliente original NO tiene esa capacidad (control).
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.resilient_connector import ResilientConnector


async def _noop_sleep(_seconds):
    """Sleep falso: no espera de verdad -> test instantáneo y determinista."""
    return None


def make_connect_that_fails(n_failures):
    """
    Fabrica una corrutina `connect_once` que falla las primeras `n_failures`
    veces y luego "conecta" (devuelve True). Lleva su propio contador.
    """
    state = {"calls": 0}

    async def connect_once():
        state["calls"] += 1
        if state["calls"] <= n_failures:
            raise ConnectionError(f"fallo simulado #{state['calls']}")
        return True

    return connect_once, state


async def test_reintenta_y_conecta():
    connector = ResilientConnector(base_delay=0.01, max_delay=0.1,
                                   max_retries=None, sleep_fn=_noop_sleep)
    connect_once, state = make_connect_that_fails(3)   # falla 3, luego conecta
    result = await connector.connect(connect_once)
    assert result is True, "❌ Debía acabar conectando"
    assert state["calls"] == 4, f"❌ Debía intentar 4 veces, fueron {state['calls']}"
    print("✅ (A) Reintenta y conecta tras 3 fallos (4º intento OK).")


async def test_agota_reintentos():
    connector = ResilientConnector(base_delay=0.01, max_delay=0.1,
                                   max_retries=2, sleep_fn=_noop_sleep)
    connect_once, _ = make_connect_that_fails(10)      # siempre falla
    try:
        await connector.connect(connect_once)
        raise AssertionError("❌ Debía lanzar ConnectionError")
    except ConnectionError:
        print("✅ (B) Agota reintentos y lanza ConnectionError.")


def test_backoff_acotado():
    connector = ResilientConnector(base_delay=1.0, max_delay=30.0)
    for attempt in range(1, 20):
        d = connector.backoff(attempt)
        assert 0 <= d <= connector.max_delay, f"❌ backoff fuera de rango: {d}"
    print("✅ (C) Backoff siempre acotado por max_delay.")


async def test_subclase_pocket_option():
    # Importamos aquí para que un fallo de dependencia no rompa los otros tests.
    from bot.resilient_pocket_option import ResilientPocketOptionClient
    from broker.pocket_option_client import PocketOptionClient

    # Subclase de prueba que simula 2 fallos de conexión y luego éxito, SIN red.
    class _FakeResilient(ResilientPocketOptionClient):
        def __init__(self, config, **kw):
            super().__init__(config, **kw)
            self._n = 0

        async def _connect_once(self):
            self._n += 1
            if self._n <= 2:
                raise ConnectionError("corte simulado")
            self._connected = True
            return True

    cfg = {"paper_trading": True, "ssid": "demo"}
    client = _FakeResilient(cfg, base_delay=0.01, max_delay=0.1,
                            sleep_fn=_noop_sleep)
    ok = await client.connect()
    assert ok is True and client.is_connected(), "❌ La subclase debía reconectar"
    assert client.is_paper() is True, "❌ Debe seguir en modo demo por seguridad"
    print("✅ (D) La subclase reconecta y conserva el modo demo (sin tocar el original).")

    # Control: el cliente ORIGINAL no tiene reconexión (su connect es de 1 intento).
    assert not hasattr(PocketOptionClient, "_connector"), \
        "❌ El original no debería tener reconexión"
    print("✅ (D-bis) El cliente original queda intacto (sin reconexión).")


if __name__ == "__main__":
    asyncio.run(test_reintenta_y_conecta())
    asyncio.run(test_agota_reintentos())
    test_backoff_acotado()
    asyncio.run(test_subclase_pocket_option())
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
