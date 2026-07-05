"""
bot/profiles.py
===============
PERFILES de bot: la decisión del usuario de tener DOS bots separados (OTC y REAL)
se concreta aquí. El MOTOR es el mismo (velas, indicadores, deep_analysis,
scoring); lo que cambia por bot es la CONFIGURACIÓN — y eso vive en un perfil.

Así cumplimos la Regla 1 (modular, sin duplicar): un solo código, dos perfiles.
Cada lanzador arranca su bot con su perfil; corren como procesos independientes.

Diferencias clave OTC vs REAL:
  - OTC: 24/7, velas sintéticas de PO, escalera desde 5s (sub-minuto útil),
    sin filtro de horario ni de noticias. Datos: solo Pocket Option.
  - REAL: Lun-Vie con horario, más inestable (noticias/volatilidad), sin
    sub-minuto (las fuentes reales no lo dan), escalera desde 1m. El bot DEBE
    callar en huecos/cierres y avisar en alta volatilidad (protección).
    Datos: Pocket Option + TradingView (CSV, 5+ años) + yfinance de respaldo.
"""

from dataclasses import dataclass, field
from typing import List, Tuple


# Escalera de LECTURA: ambos leen TODA la escala 5s..1d (el usuario quiere la
# DATA de todos los tiempos). Un tiempo sin >=6 velas se ignora solo, así que si
# una fuente no da sub-minuto real, simplemente no ensucia la lectura.
# OJO: leer != operar. El sub-minuto se LEE como contexto, pero el menú del bot
# real NO ofrece entradas de 5s (empieza en 1m); el usuario no opera 5s.
LADDER_OTC: Tuple[int, ...] = (5, 10, 15, 30, 60, 120, 180, 240, 300, 600, 900,
                               1800, 3600, 7200, 14400, 86400)
LADDER_REAL: Tuple[int, ...] = LADDER_OTC          # misma escala; se lee todo

# Majors por defecto de cada bot.
OTC_MAJORS: List[str] = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
                         "USDCAD_otc", "AUDCAD_otc", "EURJPY_otc", "GBPJPY_otc",
                         "EURGBP_otc", "USDCHF_otc"]
# REAL: SOLO MONEDAS (decisión firme del usuario). NADA de cripto (BTC/ETH) ni
# metales: ese bot es exclusivamente pares de divisas. Lista COMPLETA del menú
# real de Pocket Option (22 pares forex, tal cual aparecen en la app).
REAL_MAJORS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "GBPJPY", "GBPAUD",
    "GBPCAD", "GBPCHF", "AUDJPY", "AUDCAD", "AUDNZD", "CADJPY", "CHFJPY",
    "NZDJPY"]

# Símbolos vetados en el bot REAL (cripto/metales): NO son monedas.
_NO_MONEDAS = ("BTC", "ETH", "LTC", "XRP", "DOGE", "XAU", "XAG", "GOLD", "OIL")


@dataclass(frozen=True)
class Profile:
    """Configuración de UN bot. `frozen` = inmutable (no se toca en caliente)."""
    nombre: str                     # "OTC" | "REAL" (clave interna)
    titulo: str                     # nombre VISIBLE del bot (Telegram/logs)
    es_otc: bool                    # los activos llevan sufijo _otc
    ladder: Tuple[int, ...]         # escalera de tiempos que lee el motor
    respeta_horario: bool           # True -> no opera fuera de sesión (real)
    filtro_volatilidad: bool        # True -> avisa/calla en alta volatilidad
    fuentes_datos: Tuple[str, ...]  # de dónde saca el historial
    activos: Tuple[str, ...]        # watchlist por defecto
    db_path: str                    # base de datos PROPIA (bots separados)
    datasets_dir: str               # carpeta PROPIA en la nube (sin mezclar)
    usa_sistema: bool = False        # True -> el bot usa el SISTEMA del trader
    sub_minuto: bool = field(init=False)

    def __post_init__(self):
        # sub_minuto se deriva de la escalera (hay tiempos < 60s).
        object.__setattr__(self, "sub_minuto", any(t < 60 for t in self.ladder))
        self._validar()

    def _validar(self):
        if self.nombre not in ("OTC", "REAL"):
            raise ValueError(f"perfil desconocido: {self.nombre}")
        if not self.ladder or any(t <= 0 for t in self.ladder):
            raise ValueError("ladder inválida")
        if self.es_otc and not self.sub_minuto:
            # OTC sin sub-minuto sería raro (perdería su ventaja).
            raise ValueError("perfil OTC debería incluir tiempos sub-minuto")
        if not self.fuentes_datos:
            raise ValueError("un perfil necesita al menos una fuente de datos")
        # El bot REAL es SOLO monedas: veta cripto/metales (decisión del usuario).
        if self.nombre == "REAL":
            for a in self.activos:
                if any(x in a.upper() for x in _NO_MONEDAS):
                    raise ValueError(f"bot REAL es solo monedas: {a} no permitido")


def _ruta(*partes):
    """Ruta absoluta desde la raíz del proyecto."""
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(raiz, *partes)


# BD por bot. OTC conserva 'history.db' (donde ya está lo descargado, no se pierde);
# REAL usa la suya. Datasets en carpetas separadas para que la nube no mezcle.
# Convención de nombres (para identificar bots cuando haya muchos):
#   Fuzion <Plataforma> <Mercado>   ej: "Fuzion POption OTC", "Fuzion POption FX".
# POption = Pocket Option. Si entra otra plataforma, se distingue sola.
OTC_PROFILE = Profile(
    nombre="OTC", titulo="Fuzion POption OTC", es_otc=True, ladder=LADDER_OTC,
    respeta_horario=False, filtro_volatilidad=False,
    fuentes_datos=("pocket_option",),
    activos=tuple(OTC_MAJORS),
    db_path=_ruta("history.db"), datasets_dir=_ruta("datasets", "otc"),
    usa_sistema=True)                # FUSIÓN: tarjeta RICA (chart, VWAP, panel,
                                     # hora de entrada, Pago, Mejores) DECIDIDA por
                                     # el SISTEMA EXACTO del trader (10 indicadores,
                                     # 7/12, ley EMA200-1H, filtros). Lo mejor de
                                     # ambos: ver bonito + votar con su sistema.

REAL_PROFILE = Profile(
    nombre="REAL", titulo="Fuzion POption FX", es_otc=False, ladder=LADDER_REAL,
    respeta_horario=True, filtro_volatilidad=True,
    fuentes_datos=("pocket_option", "tradingview", "yfinance"),
    activos=tuple(REAL_MAJORS),
    db_path=_ruta("history_real.db"), datasets_dir=_ruta("datasets", "real"),
    usa_sistema=False)               # real: se activa el domingo (mercado abierto)


def get_profile(nombre):
    """Devuelve el perfil por nombre ('OTC' | 'REAL'), sin importar mayúsculas."""
    n = (nombre or "").strip().upper()
    if n == "OTC":
        return OTC_PROFILE
    if n == "REAL":
        return REAL_PROFILE
    raise ValueError(f"perfil desconocido: {nombre} (usa 'OTC' o 'REAL')")
