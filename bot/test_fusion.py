"""
bot/test_fusion.py
==================
Valida la FUSIÓN (sin red): la tarjeta rica DECIDIDA por el sistema del trader.
_fusionar_sistema mete el veredicto/dirección/alineación del sistema exacto en el
`result` de la tarjeta rica, y la protección (vacío/manipulación) manda.
"""

import bot.telegram_signals as tg


def _result_rico():
    return {"veredicto": "🟡 OPCIONAL", "direccion": "⬆️ UP (CALL)", "fuerza": 0.5,
            "coinciden": "5/10",
            "por_tiempo": {5: {"dir": "CALL", "conf": 0.2, "velas": 100},
                           60: {"dir": "CALL", "conf": 0.2, "velas": 100},
                           1800: {"dir": "CALL", "conf": 0.2, "velas": 100}}}


def _res_sistema(veredicto="NO OPERAR"):
    return {"direccion_1h": "PUT", "veredicto": veredicto, "alineados": 8,
            "total_tf": 12, "peso_favor": 80,
            "dir_por_tf": {5: "PUT", 60: "CALL", 1800: "PUT"}}


def test_fusion_manda_el_sistema():
    r = _result_rico()
    tg._fusionar_sistema(r, _res_sistema("NO OPERAR"))
    assert r["veredicto"] == "🚫 NO OPERAR"
    assert "PUT" in r["direccion"]                 # dirección del sistema (1H)
    assert r["coinciden"] == "8/12"                # alineación del sistema
    assert abs(r["fuerza"] - 0.80) < 0.01          # peso del sistema
    assert r["por_tiempo"][5]["dir"] == "PUT"      # panel: dirección del sistema
    assert r["por_tiempo"][5]["conf"] == 0.2       # conserva la conf% fina
    print("OK la tarjeta rica se decide con el sistema del trader")


def test_fusion_operar_cuando_el_sistema_lo_dice():
    r = _result_rico()
    tg._fusionar_sistema(r, _res_sistema("OPERAR"))
    assert r["veredicto"] == "✅ OPERAR"
    print("OK OPERAR cuando el sistema lo aprueba")


def test_proteccion_manda_sobre_operar():
    # El sistema dice OPERAR, pero el motor rico detectó VACÍO -> NO OPERAR.
    r = _result_rico(); r["vacio"] = ["sin flujo de precios"]
    tg._fusionar_sistema(r, _res_sistema("OPERAR"))
    assert r["veredicto"] == "🚫 NO OPERAR"
    # Lo mismo con manipulación.
    r2 = _result_rico(); r2["manipulacion"] = ["spike anormal"]
    tg._fusionar_sistema(r2, _res_sistema("OPERAR"))
    assert r2["veredicto"] == "🚫 NO OPERAR"
    print("OK protección (vacío/manipulación) bloquea aunque el sistema diga OPERAR")


if __name__ == "__main__":
    test_fusion_manda_el_sistema()
    test_fusion_operar_cuando_el_sistema_lo_dice()
    test_proteccion_manda_sobre_operar()
    print("\nTODOS OK — fusión sistema del trader + tarjeta rica")
