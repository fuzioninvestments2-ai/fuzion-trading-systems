"""
bot/test_void_detector.py
=========================
Valida el detector de VACÍO DEL MERCADO (huecos/silencio en el flujo). Sin red,
determinista (usa timestamps fijos, no reloj real).
"""

from bot.void_detector import detect_void


def _flujo_normal(n=120, t0=1000.0, step=1.0):
    """Ticks sanos: uno por segundo, precio variando."""
    return [(t0 + i * step, 1.10 + (i % 5) * 0.0001) for i in range(n)]


def test_flujo_normal_no_es_vacio():
    r = detect_void(_flujo_normal())
    assert r["void"] is False, r
    print("OK flujo normal -> sin vacío")


def test_pocos_ticks_es_vacio():
    r = detect_void([(1000.0, 1.1)])
    assert r["void"] is True and r["reasons"]
    print("OK pocos ticks -> vacío")


def test_hueco_interno_es_vacio():
    # Flujo normal pero con un salto de 20s en medio (feed caído un rato).
    t = _flujo_normal(40)
    hueco = [(ts + 20.0, p) for ts, p in _flujo_normal(40, t0=t[-1][0] + 20.0)]
    r = detect_void(t + hueco, gap_max=6.0)
    assert r["void"] is True
    assert any("hueco" in x for x in r["reasons"]), r["reasons"]
    assert r["max_gap"] >= 20.0
    print(f"OK hueco interno -> vacío (max_gap={r['max_gap']}s)")


def test_feed_congelado_es_vacio():
    # 'now' está 15s por delante del último tick -> feed viejo/congelado.
    t = _flujo_normal(30)
    r = detect_void(t, now=t[-1][0] + 15.0, stale_max=8.0)
    assert r["void"] is True
    assert any("congelado" in x for x in r["reasons"]), r["reasons"]
    print(f"OK feed congelado -> vacío (staleness={r['staleness']}s)")


def test_densidad_baja_es_vacio():
    # Un tick cada 10s -> densidad 0.1 ticks/s (por debajo del mínimo 0.25).
    t = _flujo_normal(30, step=10.0)
    r = detect_void(t, gap_max=100.0, min_density=0.25)
    assert r["void"] is True
    assert any("escaso" in x for x in r["reasons"]), r["reasons"]
    print(f"OK densidad baja -> vacío (density={r['density']} ticks/s)")


if __name__ == "__main__":
    test_flujo_normal_no_es_vacio()
    test_pocos_ticks_es_vacio()
    test_hueco_interno_es_vacio()
    test_feed_congelado_es_vacio()
    test_densidad_baja_es_vacio()
    print("\nTODOS OK — detector de vacío de mercado")
