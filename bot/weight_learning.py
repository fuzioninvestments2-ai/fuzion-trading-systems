"""
bot/weight_learning.py
======================
APRENDIZAJE de pesos por indicador: mide, sobre el historial de un activo, qué
tan acertado ha sido CADA indicador, y propone subir el peso de los que aciertan
más y bajar el de los que fallan.

EL PORQUÉ (tu visión de "aprendizaje continuo"): no todos los indicadores sirven
igual en todos los activos. En un par muy tendencial, las medias aciertan; en
uno lateral, los osciladores. En vez de fijar los pesos a mano, dejamos que el
HISTORIAL diga cuáles han funcionado en ESE activo.

Método (honesto y simple): para cada vela pasada con suficiente historia, se mira
qué votó cada indicador (CALL/PUT) y si ACERTÓ la dirección de la vela siguiente.
El "hit-rate" (aciertos/votos) se convierte en un multiplicador de peso:
  - 50% de acierto (azar) -> multiplicador 1.0 (sin cambio).
  - más del 50%           -> peso mayor (hasta un tope).
  - menos del 50%         -> peso menor (hasta un suelo).

⚠️ HONESTIDAD: acertar en el pasado NO garantiza el futuro, y en OTC (sintético)
menos aún. Esto ajusta la CONFIANZA relativa entre indicadores, no adivina. Con
poca muestra por indicador, se deja el peso neutro (1.0) para no sobreajustar.

SRP: solo calcula multiplicadores. No opera ni conecta a red. Reutiliza el motor
de scoring existente (no reimplementa indicadores).
"""

from bot.scoring_strategy import ScoringStrategy, BASE_WEIGHTS, CALL, PUT
from bot.config import get_preset


def learn_weights(candles_df, expiry_horizon=1, min_history=30, min_votes=12,
                  max_mult=1.6, min_mult=0.5):
    """
    Devuelve dict {multipliers: {ind: factor}, stats: {ind: {...}}} o None si no
    hay datos suficientes.

    expiry_horizon: cuántas velas después se mide el resultado (como en binarias).
    min_history   : velas mínimas antes de empezar a evaluar (indicadores lentos).
    min_votes     : votos mínimos de un indicador para ajustarlo (si no, 1.0).
    max_mult/min_mult: topes del multiplicador (evitan extremos por ruido).

    Nota: las medias móviles (SMA200) no votan hasta tener ~200 velas; hasta
    entonces acumulan pocos votos y quedan en 1.0 (neutro). Es correcto: no
    juzgamos un indicador con muestra insuficiente.
    """
    if candles_df is None or len(candles_df) < (min_history + min_votes):
        return None

    strat = ScoringStrategy(get_preset("agresivo"))
    hits = {k: 0 for k in BASE_WEIGHTS}
    total = {k: 0 for k in BASE_WEIGHTS}
    n = len(candles_df)

    for i in range(min_history, n - expiry_horizon):
        window = candles_df.iloc[: i + 1]
        _, _, det = strat.analyze(window)
        votes = det.get("votes", {})
        entry = float(candles_df["close"].iloc[i])
        exit_ = float(candles_df["close"].iloc[i + expiry_horizon])
        if entry == exit_:
            continue                                # empate: no cuenta
        subio = exit_ > entry
        for name, side in votes.items():
            if side == CALL:
                total[name] += 1
                if subio:
                    hits[name] += 1
            elif side == PUT:
                total[name] += 1
                if not subio:
                    hits[name] += 1

    multipliers, stats = {}, {}
    for name in BASE_WEIGHTS:
        t = total[name]
        if t < min_votes:
            multipliers[name] = 1.0
            stats[name] = {"hit_rate": None, "votos": t}
            continue
        hr = hits[name] / t
        # Mapa lineal: 0.5 -> 1.0; cada 25% de acierto sobre el azar = ±0.5.
        mult = 1.0 + (hr - 0.5) * 2.0
        mult = max(min_mult, min(max_mult, mult))
        multipliers[name] = round(mult, 3)
        stats[name] = {"hit_rate": round(hr, 3), "votos": t}

    return {"multipliers": multipliers, "stats": stats}
