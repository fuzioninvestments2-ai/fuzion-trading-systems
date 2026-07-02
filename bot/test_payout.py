"""
bot/test_payout.py
==================
Valida la extracción ROBUSTA del payout desde updateAssets de Pocket Option.
Sin red, determinista.
"""

from bot.payout import (extract_payout, parse_assets,
                        PAYOUT_MIN, PAYOUT_MAX)


def test_indice_observado():
    # Formato observado: payout en índice 5.
    a = [5, "EURUSD_otc", "EUR/USD OTC", "currency", 2, 92, 1, 1]
    assert extract_payout(a) == 92.0
    print("OK payout en índice observado (a[5]=92)")


def test_indice_movido_lo_encuentra_por_rango():
    # Si PO reordena y el payout NO está en a[5] sino más allá, el fallback por
    # rango lo encuentra igual (aquí a[5] es un id pequeño fuera de rango).
    a = [5, "GBPUSD_otc", "GBP/USD OTC", "currency", 2, 3, 87]
    assert extract_payout(a) == 87.0
    print("OK payout encontrado por rango cuando el índice cambia")


def test_rechaza_valores_fuera_de_rango():
    # Sin ningún número plausible como payout -> None (no inventa).
    a = [999, "XAU_otc", "Gold OTC", "commodity", 2, 5, 3]
    assert extract_payout(a) is None
    print("OK no inventa payout si no hay candidato plausible")


def test_limites_de_rango():
    assert extract_payout([1, "A", "a", "t", 0, PAYOUT_MAX]) == float(PAYOUT_MAX)
    assert extract_payout([1, "B", "b", "t", 0, PAYOUT_MIN]) == float(PAYOUT_MIN)
    assert extract_payout([1, "C", "c", "t", 0, PAYOUT_MAX + 1]) is None
    print("OK límites de rango (MIN/MAX incluidos, fuera excluido)")


def test_parse_assets_dict():
    assets = [
        [5, "EURUSD_otc", "EUR/USD OTC", "currency", 2, 92],
        [7, "GBPJPY_otc", "GBP/JPY OTC", "currency", 2, 78],
        ["basura"],                       # entrada inválida -> ignorada
        [9, "NODATA", "x", "t", 2, 5],    # sin payout plausible -> ignorada
    ]
    d = parse_assets(assets)
    assert d == {"EURUSD_otc": 92.0, "GBPJPY_otc": 78.0}, d
    print("OK parse_assets -> {symbol: payout}")


def test_entrada_no_lista():
    assert extract_payout(None) is None
    assert extract_payout("x") is None
    assert parse_assets(None) == {}
    print("OK entradas no-lista no rompen")


if __name__ == "__main__":
    test_indice_observado()
    test_indice_movido_lo_encuentra_por_rango()
    test_rechaza_valores_fuera_de_rango()
    test_limites_de_rango()
    test_parse_assets_dict()
    test_entrada_no_lista()
    print("\nTODOS OK — extracción robusta de payout")
