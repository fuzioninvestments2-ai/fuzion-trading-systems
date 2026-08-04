"""
tests/test_download_data.py
===========================
Validacion de `scripts/download_data.py` (TAREA 4). SIN red.

PORQUE: el script hace red (yfinance), asi que se testea la ORQUESTACION con un
loader y un repo FALSOS inyectados: se verifica el mapeo de pares, la
construccion de intervalos segun --years, el descarte de OTC y el reintento ante
fallo. Nunca se toca la red.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Sequence

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from scripts import download_data as dd   # noqa: E402


class _RepoFake:
    """Repo falso: cuenta velas guardadas, sin BD real."""

    def __init__(self, _path: str) -> None:
        self.guardadas: List[Any] = []

    def record_many(self, asset: str, tf: str, velas: Sequence[Any]) -> int:
        self.guardadas.extend(velas)
        return len(velas)

    def close(self) -> None:
        pass


def test_build_intervals_respeta_years() -> None:
    inter = dd.build_intervals(5)
    claves = {c for _i, c, _p in inter}
    assert {"M1", "tf300", "tf900", "tf1800", "tf3600", "tf86400"} == claves
    # 1h se capa a 730d aunque se pidan 5 anos (limite de yfinance).
    periodo_1h = next(p for i, _c, p in inter if i == "1h")
    assert periodo_1h == "730d"
    # diario si escala con years.
    periodo_1d = next(p for i, _c, p in inter if i == "1d")
    assert periodo_1d == "5y"


def test_years_menor_1_lanza() -> None:
    try:
        dd.build_intervals(0)
        raise AssertionError("deberia lanzar ValueError")
    except ValueError:
        pass


def test_resolve_pairs_default_y_descarta_otc() -> None:
    # Por defecto usa los pares reales del bot (config).
    por_defecto = dd.resolve_pairs(None)
    assert "EURUSD" in por_defecto and len(por_defecto) >= 18
    # Los OTC se descartan.
    mezcla = dd.resolve_pairs(["EURUSD", "GBPUSD_otc"])
    assert mezcla == ["EURUSD"]


def test_download_orquesta_sin_red() -> None:
    llamados: List[str] = []

    def loader_fake(par: str, repo: Any, intervalos: Any = None,
                    logger: Any = None) -> int:
        llamados.append(par)
        return 100        # simula 100 velas por par

    res: Dict[str, int] = dd.download(
        ["EURUSD", "GBPUSD"], db_path=":memory:",
        intervals=dd.build_intervals(2),
        loader=loader_fake, repo_factory=_RepoFake)
    assert llamados == ["EURUSD", "GBPUSD"]
    assert res == {"EURUSD": 100, "GBPUSD": 100}


def test_download_reintenta_ante_fallo() -> None:
    intentos = {"n": 0}

    def loader_flaky(par: str, repo: Any, intervalos: Any = None,
                     logger: Any = None) -> int:
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise ConnectionError("red caida")   # primer intento falla
        return 42

    # retries=3 con sleeps de 0 monkeypatch para no esperar en el test.
    _sleep_orig = dd.time.sleep
    dd.time.sleep = lambda _s: None
    try:
        res = dd.download(["EURUSD"], db_path=":memory:",
                          intervals=dd.build_intervals(1),
                          loader=loader_flaky, repo_factory=_RepoFake)
    finally:
        dd.time.sleep = _sleep_orig
    assert res["EURUSD"] == 42
    assert intentos["n"] == 2      # fallo + reintento OK


def _run_all() -> None:
    tests = [test_build_intervals_respeta_years, test_years_menor_1_lanza,
             test_resolve_pairs_default_y_descarta_otc,
             test_download_orquesta_sin_red, test_download_reintenta_ante_fallo]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
