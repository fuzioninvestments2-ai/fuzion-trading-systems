"""
scripts/download_data.py
========================
TAREA 4 del manual: descarga AUTOMATICA de historial con yfinance.

PORQUE: para backtestear y calibrar el sistema desde el primer dia hacen falta
anos de velas reales. Este script orquesta la descarga de los pares forex REALES
y las guarda en la BD (TAREA 3), reutilizando el loader ya probado del bot
(`bot/historical_loader.load_real_history`) — no se reimplementa yfinance.

Uso:
    python scripts/download_data.py --source yfinance --years 5
    python scripts/download_data.py --pairs EURUSD GBPUSD --years 2 --db history_real.db

LIMITES HONESTOS (heredados de yfinance):
  - Intradia gratuito acotado: 1m ~7d, 5m/15m/30m ~60d, 1h ~730d, diario decadas.
    `--years` afecta sobre todo a 1h y diario; el intradia corto no se puede
    estirar (limite de la fuente, no del script).
  - SOLO mercado REAL. Los OTC son sinteticos de Pocket Option: no existen en
    ninguna fuente externa y se rechazan (no se inventan datos).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from config import settings                              # noqa: E402
from bot.historical_loader import load_real_history      # noqa: E402
from src.persistence.database import Database            # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
_log = logging.getLogger("download_data")

# Tipo del loader inyectable: (par, repo, intervalos, logger) -> velas guardadas.
Loader = Callable[..., int]
Intervalo = Tuple[str, str, str]


def build_intervals(years: int) -> List[Intervalo]:
    """
    Construye la lista (interval, clave_BD, period) segun los anos pedidos.

    PORQUE: yfinance capa el intradia por rango (no depende de `years`), pero 1h
    y diario si escalan. Se respeta el tope de 1h (~730d) para no pedir de mas.
    """
    if years < 1:
        raise ValueError("--years debe ser >= 1")
    dias_1h = min(years * 365, 730)          # tope real de yfinance para 1h
    return [
        ("1m", "M1", "7d"),
        ("5m", "tf300", "60d"),
        ("15m", "tf900", "60d"),
        ("30m", "tf1800", "60d"),
        ("1h", "tf3600", f"{dias_1h}d"),
        ("1d", "tf86400", f"{years}y"),
    ]


def resolve_pairs(pairs_arg: Optional[Sequence[str]]) -> List[str]:
    """
    Devuelve la lista de pares REALES a descargar. Sin `--pairs`, usa la lista
    del bot (config.FOREX_PAIRS_REAL). Los OTC se descartan con aviso: yfinance
    no tiene datos sinteticos de PO.
    """
    if pairs_arg:
        pares = [p.upper() for p in pairs_arg]
    else:
        pares = list(settings.FOREX_PAIRS_REAL)
    limpios: List[str] = []
    for p in pares:
        if p.endswith("_OTC") or p.endswith("_otc"):
            _log.warning("Se ignora %s: OTC no tiene fuente externa real.", p)
            continue
        limpios.append(p)
    return limpios


def download(pairs: Sequence[str], db_path: str, intervals: List[Intervalo],
             loader: Loader = load_real_history,
             repo_factory: Callable[[str], object] = Database,
             retries: int = 3) -> Dict[str, int]:
    """
    Descarga cada par y lo guarda en la BD. Devuelve {par: velas_guardadas}.

    `loader` y `repo_factory` son inyectables para poder testear la orquestacion
    SIN red. Robustez (Regla 3): reintenta cada par ante fallo de red con backoff
    exponencial (2s, 4s, 8s) antes de rendirse y seguir con el siguiente.
    """
    repo = repo_factory(db_path)
    resultados: Dict[str, int] = {}
    try:
        for par in pairs:
            guardadas = 0
            for intento in range(1, retries + 1):
                try:
                    guardadas = loader(par, repo, intervalos=intervals,
                                       logger=_log)
                    break
                except Exception as e:                    # red u otro fallo
                    espera = 2 ** intento
                    _log.warning("Fallo %s (intento %d/%d): %s. Reintento en %ds.",
                                 par, intento, retries, e, espera)
                    if intento < retries:
                        time.sleep(espera)
            resultados[par] = guardadas
            _log.info("%s: %d velas.", par, guardadas)
    finally:
        cerrar = getattr(repo, "close", None)
        if callable(cerrar):
            cerrar()
    return resultados


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Descarga historial real con yfinance.")
    p.add_argument("--source", default="yfinance", choices=["yfinance"],
                   help="Fuente de datos (por ahora solo yfinance).")
    p.add_argument("--years", type=int, default=5,
                   help="Anos de historial (afecta a 1h y diario).")
    p.add_argument("--pairs", nargs="*", default=None,
                   help="Pares concretos (por defecto los 22 reales del bot).")
    p.add_argument("--db", default=settings.DB_REAL_PATH,
                   help="Ruta de la BD destino.")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    intervals = build_intervals(args.years)
    pares = resolve_pairs(args.pairs)
    _log.info("Descargando %d pares (%s, %d anos) -> %s",
              len(pares), args.source, args.years, args.db)
    resultados = download(pares, args.db, intervals)
    total = sum(resultados.values())
    ok = sum(1 for v in resultados.values() if v > 0)
    _log.info("Listo: %d/%d pares con datos, %d velas en total.",
              ok, len(pares), total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
