"""
bot/resilient_pocket_option.py
==============================
Cliente de Pocket Option con RECONEXIÓN ROBUSTA, SIN modificar el original.

El `broker/pocket_option_client.py` existente conecta una sola vez y, si falla,
lanza una excepción (no reintenta). Esta SUBCLASE le añade reconexión con
backoff exponencial reutilizando `ResilientConnector`, respetando el principio
ABIERTO/CERRADO de SOLID: extendemos el comportamiento sin tocar el archivo
original (cero riesgo para el sistema existente).

⚠️ Igual que el original: las opciones binarias son de ALTO RIESGO. Esta clase
hereda el modo demo por defecto (paper_trading=True) y NO cambia esa seguridad.
"""

from broker.pocket_option_client import PocketOptionClient
from bot.resilient_connector import ResilientConnector


class ResilientPocketOptionClient(PocketOptionClient):
    """
    PocketOptionClient + reconexión automática.

    Sobrescribe `connect()` para envolver el intento del padre con reintentos.
    Mantiene intactos todos los demás métodos (órdenes, datos, etc.).
    """

    def __init__(self, config, *, base_delay=1.0, max_delay=30.0,
                 max_retries=None, logger=None, sleep_fn=None, rng=None):
        super().__init__(config)
        # Permitimos inyectar sleep_fn/rng para tests deterministas; si no se
        # pasan, ResilientConnector usa sus valores por defecto (asyncio.sleep).
        kwargs = {"base_delay": base_delay, "max_delay": max_delay,
                  "max_retries": max_retries, "logger": logger}
        if sleep_fn is not None:
            kwargs["sleep_fn"] = sleep_fn
        if rng is not None:
            kwargs["rng"] = rng
        self._connector = ResilientConnector(**kwargs)

    async def _connect_once(self):
        """
        Un ÚNICO intento de conexión: delega en la implementación del padre, que
        no reintenta. Aislarlo aquí permite testear la reconexión sin red real
        (en pruebas se sobrescribe este método para simular fallos).
        """
        return await super().connect()

    async def connect(self) -> bool:
        """
        Conecta con reintentos + backoff. Si el primer intento falla, espera y
        vuelve a intentar (a diferencia del padre, que se rendía al primer fallo).
        """
        return await self._connector.connect(self._connect_once)
