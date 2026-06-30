"""
validation/test_timestamp_guard.py
==================================
Prueba de validación del guardia de timestamp (Regla 4).

Usamos un "ahora" FIJO inyectado para que la prueba sea determinista (no
depende del reloj real). Fijamos el sistema en t = 1_000_000 ms y variamos el
timestamp del bróker para cubrir todos los casos.

Verifica:
  (A) Deriva pequeña (dentro de 500 ms) -> señal PERMITIDA.
  (B) Deriva grande (más de 500 ms)     -> señal DESCARTADA.
  (C) Borde exacto (500 ms)             -> PERMITIDA (comparación '<=').
  (D) Simetría: da igual si el bróker va por delante o por detrás.
"""

from timestamp_guard import TimestampGuard

# Reloj del sistema fijo para la prueba (ms desde época, valor arbitrario).
NOW = 1_000_000.0


def make_guard():
    # Inyectamos un "ahora" constante -> prueba determinista.
    return TimestampGuard(max_drift_ms=500.0, now_ms_provider=lambda: NOW)


def test_dentro_del_umbral():
    g = make_guard()
    # Bróker 200 ms por detrás -> deriva 200 ms -> permitido.
    allowed, drift = g.check(NOW - 200)
    assert allowed and abs(drift - 200) < 1e-9, f"❌ deriva={drift}, allowed={allowed}"
    print(f"✅ (A) Deriva 200 ms -> PERMITIDA (drift={drift:.1f} ms).")


def test_fuera_del_umbral():
    g = make_guard()
    # Bróker 800 ms por delante -> deriva 800 ms -> descartado.
    allowed, drift = g.check(NOW + 800)
    assert (not allowed) and abs(drift - 800) < 1e-9, f"❌ deriva={drift}, allowed={allowed}"
    print(f"✅ (B) Deriva 800 ms -> DESCARTADA (drift={drift:.1f} ms).")


def test_borde_exacto():
    g = make_guard()
    # Deriva EXACTA de 500 ms -> debe permitirse (regla '<=').
    allowed_500, drift_500 = g.check(NOW - 500)
    assert allowed_500 and abs(drift_500 - 500) < 1e-9, f"❌ borde 500: {drift_500}"
    # Deriva de 501 ms -> ya debe descartarse.
    allowed_501, _ = g.check(NOW - 501)
    assert not allowed_501, "❌ 501 ms debería descartarse"
    print("✅ (C) Borde: 500 ms PERMITIDA, 501 ms DESCARTADA.")


def test_simetria():
    g = make_guard()
    # Misma magnitud de deriva por delante y por detrás -> misma decisión.
    a_delante, d_delante = g.check(NOW + 300)
    a_detras, d_detras = g.check(NOW - 300)
    assert a_delante == a_detras and abs(d_delante - d_detras) < 1e-9, "❌ asimetría"
    print("✅ (D) Simetría: ±300 ms se tratan igual (deriva absoluta).")


if __name__ == "__main__":
    test_dentro_del_umbral()
    test_fuera_del_umbral()
    test_borde_exacto()
    test_simetria()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
