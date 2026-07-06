"""
bot/test_validacion_senal.py
============================
Valida SIN red la puerta de calidad validate_signal: una señal PERFECTA pasa; si
CUALQUIER regla falla, se rechaza con el motivo exacto.
"""
from bot.validacion_senal import validate_signal


def _buena():
    """Señal que cumple TODAS las reglas."""
    return {
        "direccion": "CALL",
        "alineacion_pct": 85.0,
        "tiempos_presentes": 12, "tiempos_config": 12,
        "win_rate_hist": 0.66, "senales_medidas": 30,
        "umbral_aprendido": 0.30,
        "indicadores": {"RSI": 0.64, "Estocástico": 0.62, "MACD": 0.61, "Bandas": 0.66},
        "cerca_sr": False, "dist_sr_pips": 25.0,
        "conf_por_tiempo": {60: 0.62, 300: 0.65, 900: 0.63, 3600: 0.72},
    }


def test_senal_perfecta_opera():
    r = validate_signal(_buena())
    assert r["operar"] is True, r
    print("OK señal de alta calidad -> OPERAR")


def test_faltan_tiempos_rechaza():
    d = _buena(); d["tiempos_presentes"] = 9
    r = validate_signal(d)
    assert not r["operar"] and "faltan" in r["motivo"], r
    print("OK faltan tiempos -> rechazo:", r["motivo"])


def test_alineacion_baja_rechaza():
    d = _buena(); d["alineacion_pct"] = 67.0
    r = validate_signal(d)
    assert not r["operar"] and "Alineación 67% < 80%" in r["motivo"], r
    print("OK", r["motivo"])


def test_winrate_bajo_rechaza():
    d = _buena(); d["win_rate_hist"] = 0.49
    r = validate_signal(d)
    assert not r["operar"] and "win-rate 49% < 60%" in r["motivo"], r
    print("OK", r["motivo"])


def test_winrate_sin_historial_no_bloquea_en_arranque():
    # Con pocas señales medidas aún no se puede exigir 60% (no se inventa).
    d = _buena(); d["win_rate_hist"] = None; d["senales_medidas"] = 3
    assert validate_signal(d)["operar"] is True
    print("OK arranque sin historial: la regla de win-rate espera datos")


def test_indicador_en_ruido_rechaza():
    d = _buena(); d["indicadores"]["RSI"] = 0.52     # 45-55% = ruido
    r = validate_signal(d)
    assert not r["operar"] and "ruido" in r["motivo"], r
    print("OK", r["motivo"])


def test_indicador_bajo_rechaza():
    d = _buena(); d["indicadores"]["MACD"] = 0.40
    r = validate_signal(d)
    assert not r["operar"] and "MACD 40% < 60%" in r["motivo"], r
    print("OK", r["motivo"])


def test_pegado_a_sr_rechaza():
    d = _buena(); d["cerca_sr"] = True; d["dist_sr_pips"] = 8.0
    r = validate_signal(d)
    assert not r["operar"] and "pegado a soporte/resistencia" in r["motivo"], r
    print("OK", r["motivo"])


def test_confirmacion_tiempo_baja_rechaza():
    d = _buena(); d["conf_por_tiempo"][3600] = 0.62   # 1h pide 70%
    r = validate_signal(d)
    assert not r["operar"] and "1H" in r["motivo"], r
    print("OK", r["motivo"])


def test_umbral_bajo_rechaza():
    d = _buena(); d["umbral_aprendido"] = 0.20
    r = validate_signal(d)
    assert not r["operar"] and "umbral aprendido 20% < 25%" in r["motivo"], r
    print("OK", r["motivo"])


if __name__ == "__main__":
    test_senal_perfecta_opera()
    test_faltan_tiempos_rechaza()
    test_alineacion_baja_rechaza()
    test_winrate_bajo_rechaza()
    test_winrate_sin_historial_no_bloquea_en_arranque()
    test_indicador_en_ruido_rechaza()
    test_indicador_bajo_rechaza()
    test_pegado_a_sr_rechaza()
    test_confirmacion_tiempo_baja_rechaza()
    test_umbral_bajo_rechaza()
    print("\nTODOS OK — puerta de calidad validate_signal")
