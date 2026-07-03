"""
bot/test_profiles.py
====================
Valida los perfiles OTC/REAL (la separación en dos bots) SIN red.
"""

from bot.profiles import (get_profile, OTC_PROFILE, REAL_PROFILE,
                          LADDER_OTC, LADDER_REAL, Profile)


def test_get_profile():
    assert get_profile("otc") is OTC_PROFILE
    assert get_profile("REAL") is REAL_PROFILE
    try:
        get_profile("xyz")
        assert False, "debería fallar con perfil desconocido"
    except ValueError:
        pass
    print("OK get_profile devuelve OTC/REAL y rechaza desconocidos")


def test_otc_tiene_sub_minuto_y_es_24_7():
    assert OTC_PROFILE.es_otc is True
    assert OTC_PROFILE.sub_minuto is True and 5 in OTC_PROFILE.ladder
    assert OTC_PROFILE.respeta_horario is False       # 24/7
    assert OTC_PROFILE.filtro_volatilidad is False
    assert OTC_PROFILE.fuentes_datos == ("pocket_option",)
    print("OK perfil OTC: sub-minuto, 24/7, solo Pocket Option")


def test_real_sin_sub_minuto_con_horario_y_fuentes():
    assert REAL_PROFILE.es_otc is False
    assert REAL_PROFILE.sub_minuto is False and min(REAL_PROFILE.ladder) == 60
    assert REAL_PROFILE.respeta_horario is True        # Lun-Vie, sesión
    assert REAL_PROFILE.filtro_volatilidad is True     # protección noticias
    assert "tradingview" in REAL_PROFILE.fuentes_datos
    assert "yfinance" in REAL_PROFILE.fuentes_datos
    assert all(not a.endswith("_otc") for a in REAL_PROFILE.activos)
    print("OK perfil REAL: sin sub-minuto, horario, volatilidad, PO+TV+yfinance")


def test_real_solo_monedas_sin_cripto():
    # Decisión firme: el bot REAL es SOLO monedas. Nada de cripto/metales.
    prohibidos = ("BTC", "ETH", "XAU", "XAG", "GOLD", "OIL")
    for a in REAL_PROFILE.activos:
        assert not any(x in a.upper() for x in prohibidos), a
    # Y el perfil debe RECHAZAR crear un REAL con cripto.
    try:
        Profile(nombre="REAL", es_otc=False, ladder=LADDER_REAL,
                respeta_horario=True, filtro_volatilidad=True,
                fuentes_datos=("yfinance",), activos=("BTCUSD",),
                db_path=":memory:")
        assert False, "debería rechazar cripto en REAL"
    except ValueError:
        pass
    print("OK bot REAL es SOLO monedas (cripto/metales rechazados)")


def test_bases_de_datos_separadas():
    # Bots independientes => historial en BD distinta.
    assert OTC_PROFILE.db_path != REAL_PROFILE.db_path
    assert OTC_PROFILE.db_path.endswith("history_otc.db")
    assert REAL_PROFILE.db_path.endswith("history_real.db")
    print("OK cada bot usa su propia base de datos")


def test_perfil_otc_sin_sub_minuto_falla():
    # Un OTC sin sub-minuto perdería su ventaja: debe rechazarse.
    try:
        Profile(nombre="OTC", es_otc=True, ladder=(60, 300),
                respeta_horario=False, filtro_volatilidad=False,
                fuentes_datos=("pocket_option",), activos=("EURUSD_otc",),
                db_path=":memory:")
        assert False, "debería fallar"
    except ValueError:
        pass
    print("OK OTC sin sub-minuto es inválido")


if __name__ == "__main__":
    test_get_profile()
    test_otc_tiene_sub_minuto_y_es_24_7()
    test_real_sin_sub_minuto_con_horario_y_fuentes()
    test_real_solo_monedas_sin_cripto()
    test_bases_de_datos_separadas()
    test_perfil_otc_sin_sub_minuto_falla()
    print("\nTODOS OK — perfiles OTC/REAL (dos bots separados)")
