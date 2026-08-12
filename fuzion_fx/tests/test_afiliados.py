"""
tests/test_afiliados.py (fuzion_fx)
===================================
Valida el registro de afiliados y la membresia mensual: alta, marcar_pagado
(extiende/renueva), destinatarios por temporalidad (solo activos), baja y cobro.
SIN red (sqlite temporal).
"""

from __future__ import annotations

import os
import sys
import tempfile

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from core import afiliados                                       # noqa: E402

T0 = 1_000_000_000
DIA = 86400


def _db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def test_alta_y_estado() -> None:
    db = _db()
    try:
        aid = afiliados.alta("Juan", "111", ["f1_m1", "f3_m3"], fee=20, dias=30,
                             now=T0, db_path=db)
        lst = afiliados.listar(now=T0, db_path=db)
        assert len(lst) == 1 and lst[0]["activo"] is True
        assert lst[0]["dias_restantes"] == 30 and lst[0]["fee"] == 20
        # A los 40 dias esta vencido.
        assert afiliados.listar(now=T0 + 40 * DIA, db_path=db)[0]["activo"] is False
        _ = aid
    finally:
        os.unlink(db)


def test_marcar_pagado_renueva() -> None:
    db = _db()
    try:
        aid = afiliados.alta("Ana", "222", ["f4_m5"], dias=30, now=T0, db_path=db)
        # Vencido (t=+40d). Pagar arranca desde AHORA + 30.
        nuevo = afiliados.marcar_pagado(aid, dias=30, now=T0 + 40 * DIA, db_path=db)
        assert nuevo == T0 + 40 * DIA + 30 * DIA
        assert afiliados.listar(now=T0 + 40 * DIA, db_path=db)[0]["activo"] is True
    finally:
        os.unlink(db)


def test_destinatarios_por_temporalidad() -> None:
    db = _db()
    try:
        afiliados.alta("A", "chatA", ["f1_m1", "f2_m2"], now=T0, db_path=db)
        afiliados.alta("B", "chatB", ["f3_m3"], now=T0, db_path=db)
        v = afiliados.alta("C", "chatC", ["f1_m1"], dias=1, now=T0, db_path=db)
        # Para 1M: A y C (ambos activos en T0).
        d1 = afiliados.destinatarios_para("f1_m1", now=T0, db_path=db)
        assert sorted(x["chat_id"] for x in d1) == ["chatA", "chatC"]
        # Pasado el vencimiento de C (1 dia), 1M solo va a A.
        d2 = afiliados.destinatarios_para("f1_m1", now=T0 + 2 * DIA, db_path=db)
        assert [x["chat_id"] for x in d2] == ["chatA"]
        _ = v
    finally:
        os.unlink(db)


def test_baja_y_resumen() -> None:
    db = _db()
    try:
        a1 = afiliados.alta("A", "1", ["f1_m1"], fee=10, now=T0, db_path=db)
        afiliados.alta("B", "2", ["f2_m2"], fee=15, now=T0, db_path=db)
        r = afiliados.resumen(now=T0, db_path=db)
        assert r["total"] == 2 and r["activos"] == 2 and r["ingreso_mensual"] == 25
        afiliados.baja(a1, db_path=db)
        assert afiliados.resumen(now=T0, db_path=db)["total"] == 1
    finally:
        os.unlink(db)


def test_cobro_config() -> None:
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    try:
        assert afiliados.leer_cobro(f.name)["moneda"] == "USDT"      # default
        afiliados.set_cobro("wallet123", 25.0, "USDT", path=f.name)
        c = afiliados.leer_cobro(f.name)
        assert c["wallet"] == "wallet123" and c["precio"] == 25.0
    finally:
        os.unlink(f.name)


def _run_all() -> None:
    tests = [test_alta_y_estado, test_marcar_pagado_renueva,
             test_destinatarios_por_temporalidad, test_baja_y_resumen,
             test_cobro_config]
    for t in tests:
        t()
        print(f"  OK  {t.__name__}")
    print(f"{len(tests)} tests OK (sin red)")


if __name__ == "__main__":
    _run_all()
