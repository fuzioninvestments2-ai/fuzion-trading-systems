"""
bot/test_session.py
===================
Prueba de validación del riesgo + sesiones (Regla 4), de forma determinista.

Inyectamos una estrategia FALSA (siempre CALL) y un `execute_fn` con resultados
guionizados (gana/pierde a voluntad), para probar la lógica sin datos reales.

Verifica:
  (A) La sesión se DETIENE al alcanzar el target de ganancia.
  (B) El Martingale escala con tope y luego vuelve al base (no dobla al abismo).
  (C) La sesión PARA por pérdidas consecutivas (cinturón de seguridad).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import logging
from bot.config import get_preset, TradingConfig
from bot.risk_manager import RiskManager
from bot.session import SessionManager
from bot.scoring_strategy import CALL


def _silent():
    lg = logging.getLogger("session_test")
    lg.addHandler(logging.NullHandler())
    lg.setLevel(logging.CRITICAL)
    return lg


class _FakeStrategyCall:
    def analyze(self, df):
        return CALL, 0.9, {}


def test_target_alcanzado():
    cfg = get_preset("moderado")          # martingale off, target=5.0
    risk = RiskManager(cfg, _silent())
    sesion = SessionManager(cfg, _FakeStrategyCall(), risk,
                            execute_fn=lambda s, a: True,   # siempre gana
                            logger=_silent(), payout=0.92)
    sesion.start()
    for _ in range(200):                  # velas simuladas
        if not sesion.active:
            break
        sesion.on_candle(df=None)
    resumen = sesion.summary()
    assert not sesion.active, "❌ La sesión debía detenerse"
    assert resumen["profit"] >= cfg.target_profit, "❌ No alcanzó el target"
    assert "target" in resumen["stop_reason"], f"❌ Motivo: {resumen['stop_reason']}"
    print(f"✅ (A) Target alcanzado: {resumen}")


def test_martingale_con_tope():
    # base = 100 * 0.02 = 2.0 ; multiplier 2 ; max_steps 3.
    cfg = TradingConfig(trade_capital=100.0, stack_method="aggressive",
                        martingale_enabled=True, martingale_max_steps=3,
                        martingale_multiplier=2.0)
    risk = RiskManager(cfg, _silent())

    esperado = [2.0, 4.0, 8.0, 16.0, 2.0]  # base, y tras 1,2,3,4 pérdidas
    # Antes de perder: monto base (confianza 1.0).
    assert abs(risk.next_amount(1.0) - esperado[0]) < 1e-9
    for i in range(1, 5):
        risk.register_result(is_win=False, pnl=-1.0)  # una pérdida más
        got = risk.next_amount(1.0)
        assert abs(got - esperado[i]) < 1e-9, \
            f"❌ Tras {i} pérdidas esperaba {esperado[i]}, dio {got}"
    print("✅ (B) Martingale escala 2->4->8->16 y tras el tope vuelve a 2.")


def test_para_por_perdidas_consecutivas():
    cfg = get_preset("moderado")          # max_consecutive_losses = 5
    risk = RiskManager(cfg, _silent())
    sesion = SessionManager(cfg, _FakeStrategyCall(), risk,
                            execute_fn=lambda s, a: False,  # siempre pierde
                            logger=_silent(), payout=0.92)
    sesion.start()
    for _ in range(50):
        if not sesion.active:
            break
        sesion.on_candle(df=None)
    resumen = sesion.summary()
    assert not sesion.active, "❌ La sesión debía pararse por riesgo"
    assert resumen["stop_reason"] is not None
    print(f"✅ (C) Paró por riesgo: {resumen['stop_reason']} | {resumen}")


if __name__ == "__main__":
    test_target_alcanzado()
    test_martingale_con_tope()
    test_para_por_perdidas_consecutivas()
    print("-" * 60)
    print("✅ TODAS LAS PRUEBAS PASARON.")
