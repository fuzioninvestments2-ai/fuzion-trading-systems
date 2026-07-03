"""
bot/test_news_filter.py
=======================
Valida el filtro de noticias del bot REAL SIN red: parseo del calendario y la
ventana de bloqueo 15 min antes/después de eventos de alto impacto.
"""

import json
from datetime import datetime, timezone, timedelta

from bot.news_filter import NewsFilter, parse_eventos, _monedas_del_par


_AHORA = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)


def _calendario():
    # Un evento USD de alto impacto justo AHORA, y uno EUR lejano (2h).
    return json.dumps([
        {"country": "USD", "impact": "High",
         "date": _AHORA.isoformat()},
        {"country": "EUR", "impact": "High",
         "date": (_AHORA + timedelta(hours=2)).isoformat()},
        {"country": "GBP", "impact": "Low",
         "date": _AHORA.isoformat()},          # bajo impacto: NO bloquea
    ])


def test_monedas_del_par():
    assert _monedas_del_par("EURUSD") == {"EUR", "USD"}
    assert _monedas_del_par("eur/usd") == {"EUR", "USD"}
    assert _monedas_del_par("GBPJPY_otc") == {"GBP", "JPY"}
    print("OK extrae las dos monedas del par")


def test_parse_ignora_invalidos():
    txt = json.dumps([{"country": "USD", "impact": "High", "date": "basura"},
                      {"impact": "High", "date": _AHORA.isoformat()},  # sin país
                      {"country": "USD", "impact": "High",
                       "date": _AHORA.isoformat()}])
    assert len(parse_eventos(txt)) == 1
    print("OK parseo descarta eventos inválidos")


def test_bloquea_par_afectado_en_ventana():
    nf = NewsFilter()
    nf.cargar(_calendario())
    # USD tiene evento AHORA -> EURUSD y USDJPY bloqueados.
    assert nf.can_trade("EURUSD", _AHORA) is False
    assert nf.can_trade("USDJPY", _AHORA) is False
    # GBP solo tiene evento de BAJO impacto -> GBPAUD permitido.
    assert nf.can_trade("GBPAUD", _AHORA) is True
    print("OK bloquea pares con moneda en noticia de alto impacto")


def test_fuera_de_ventana_permite():
    nf = NewsFilter()
    nf.cargar(_calendario())
    # 30 min después del evento USD -> ya fuera de la ventana de 15 min.
    despues = _AHORA + timedelta(minutes=30)
    assert nf.can_trade("EURUSD", despues) is True
    print("OK fuera de la ventana (15m) vuelve a permitir")


def test_otc_nunca_se_bloquea():
    nf = NewsFilter()
    nf.cargar(_calendario())
    # OTC es sintético: no depende de noticias reales.
    assert nf.can_trade("EURUSD_otc", _AHORA) is True
    print("OK OTC nunca se bloquea por noticias")


def test_proximo_evento():
    nf = NewsFilter()
    nf.cargar(_calendario())
    ev = nf.proximo_evento("EURUSD", _AHORA)
    assert ev is not None and ev["moneda"] in ("EUR", "USD")
    print("OK informa el próximo evento de alto impacto del par")


if __name__ == "__main__":
    test_monedas_del_par()
    test_parse_ignora_invalidos()
    test_bloquea_par_afectado_en_ventana()
    test_fuera_de_ventana_permite()
    test_otc_nunca_se_bloquea()
    test_proximo_evento()
    print("\nTODOS OK — filtro de noticias (protección bot real)")
