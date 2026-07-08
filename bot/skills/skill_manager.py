"""
bot/skills/skill_manager.py
===========================
Combina los votos de los skills con PESOS que aprenden del resultado REAL del
mercado. Es un "bandido" simple: el skill que acierta gana peso, el que falla lo
pierde. Con el tiempo, los mejores skills mandan más.

CORRECCIÓN CLAVE vs el diseño original (honestidad):
  - Se aprende del MOVIMIENTO REAL del precio (`real_direction`), NO de la dirección
    que el bot eligió. Entrenar contra la propia decisión enseña al sistema a
    copiarse a sí mismo, no a predecir el mercado.
  - No hay ejecución de órdenes. El consenso es una SEÑAL; la orden la coloca el humano.

Persistencia: pesos y contadores en JSON; historial de señales en SQLite (opcional).
Rutas inyectables para poder testear sin tocar los archivos reales.
"""
import json
import os

from bot.skills.base_skill import CALL, PUT, NEUTRAL

PESO_INI = 1.0
PESO_MIN, PESO_MAX = 0.1, 2.0
LEARNING_RATE = 0.1


class SkillManager:
    def __init__(self, weights_path="memoria/skill_weights.json"):
        self.skills = {}
        self.weights = {}
        self.total = 0
        self.wins = 0
        self.weights_path = weights_path
        self._cargar()

    # --- registro ---
    def register_skill(self, skill):
        sid = skill.__class__.__name__
        self.skills[sid] = skill
        self.weights.setdefault(sid, PESO_INI)
        return sid

    # --- decisión ---
    def get_consensus(self, market_data):
        """
        Suma ponderada de votos. NEUTRAL no cuenta para la dirección. Devuelve
        dirección, confianza (0-0.95) y el detalle por skill (para auditar y aprender).
        """
        detalle = {}
        peso_call = peso_put = 0.0
        for sid, skill in self.skills.items():
            pred = skill.analyze(market_data)
            w = self.weights.get(sid, PESO_INI)
            detalle[sid] = {"vote": pred["direction"], "confidence": pred["confidence"],
                            "weight": w, "reason": pred["reason"]}
            score = w * pred["confidence"]
            if pred["direction"] == CALL:
                peso_call += score
            elif pred["direction"] == PUT:
                peso_put += score

        total = peso_call + peso_put
        if total == 0:
            return {"direction": NEUTRAL, "confidence": 0.0, "details": detalle}
        if peso_call >= peso_put:
            direccion, conf = CALL, peso_call / total
        else:
            direccion, conf = PUT, peso_put / total
        return {"direction": direccion, "confidence": min(conf, 0.95), "details": detalle}

    # --- aprendizaje ---
    def update_weights(self, real_direction, detalle):
        """
        Ajusta pesos según el resultado REAL. `detalle` = el dict `details` del
        consenso (voto de cada skill). Recompensa: +1 si el skill votó la dirección
        real, −1 si votó la contraria. NEUTRAL no premia ni castiga.
        """
        self.total += 1
        # win global del CONSENSO: ¿la dirección mayoritaria acertó? (para métrica)
        # se calcula fuera; aquí solo ajustamos pesos por skill.
        prom = self.wins / self.total if self.total else 0.5
        for sid, v in (detalle or {}).items():
            voto = v.get("vote")
            if voto not in (CALL, PUT):
                continue
            reward = 1.0 if voto == real_direction else -1.0
            w = self.weights.get(sid, PESO_INI)
            w = w + LEARNING_RATE * (reward - prom)
            self.weights[sid] = max(PESO_MIN, min(PESO_MAX, w))
            skill = self.skills.get(sid)
            if skill is not None:
                skill.learn({"real_direction": real_direction, "vote": voto})

    def registrar_win(self, acerto):
        """Cuenta el acierto del CONSENSO (métrica global, separada de los pesos)."""
        if acerto:
            self.wins += 1

    def best_skills(self, top_n=3):
        return [s for s, _ in sorted(self.weights.items(), key=lambda x: -x[1])][:top_n]

    def win_rate(self):
        return self.wins / self.total if self.total else 0.0

    def stats(self):
        return {"skills": len(self.skills), "total": self.total,
                "win_rate": round(self.win_rate(), 4), "best": self.best_skills(),
                "weights": {k: round(v, 3) for k, v in self.weights.items()}}

    # --- persistencia ---
    def _cargar(self):
        try:
            with open(self.weights_path) as f:
                s = json.load(f)
            self.weights = s.get("weights", {})
            self.total = s.get("total_trades", 0)
            self.wins = s.get("winning_trades", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            self.weights = {}

    def save_state(self):
        os.makedirs(os.path.dirname(self.weights_path) or ".", exist_ok=True)
        with open(self.weights_path, "w") as f:
            json.dump({"weights": self.weights, "total_trades": self.total,
                       "winning_trades": self.wins, "win_rate": self.win_rate()},
                      f, indent=2)
