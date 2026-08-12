"""
core/daily_report.py (fuzion_fx)
================================
Arma el RESUMEN DIARIO de un bot a partir de su sqlite (ResultsStore). Pieza
PURA y testeable: recibe la ventana del dia (start/end en epoch) y devuelve las
estadisticas; el formato Markdown (archivo) y el texto corto (Telegram) salen de
los mismos datos. NO usa reloj (el scheduler le pasa la fecha y la ventana), asi
se prueba sin red ni tiempo real.

Modo recuperacion: se DERIVA de la DB (perdidas consecutivas al cierre >=
recovery_after), porque el estado en memoria del RiskManager no lo ve un proceso
separado como el scheduler del resumen.

Honestidad (regla del proyecto): el resumen lleva el aviso demo/educativo; los
numeros son los reales de las senales, no promesas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class DailyReport:
    def __init__(self, store, *, bot_name: str, card_label: str,
                 recovery_after: int) -> None:
        self.store = store
        self.bot_name = bot_name
        self.card_label = card_label
        self.recovery_after = int(recovery_after)

    # ------------------------------------------------------------- calculo
    def build(self, day_start_ts: int, day_end_ts: int) -> Dict[str, Any]:
        """Estadisticas del dia [day_start_ts, day_end_ts) para este bot."""
        sigs = self.store.signals_in_range(day_start_ts, day_end_ts)
        total = len(sigs)

        por_par: Dict[str, Dict[str, Any]] = {}
        for s in sigs:
            d = por_par.setdefault(s["pair"], {"signals": 0, "wins": 0,
                                               "losses": 0, "ties": 0,
                                               "nulas": 0, "pending": 0})
            d["signals"] += 1
            if not s["resolved"]:
                d["pending"] += 1
            elif s["result"] == "win":
                d["wins"] += 1
            elif s["result"] == "loss":
                d["losses"] += 1
            elif s["result"] == "tie":
                d["ties"] += 1
            else:
                # result == 'NULL': sin dato real al vencimiento. Se registra pero
                # NO cuenta como win/loss/tie (honestidad, Paso 3).
                d["nulas"] += 1

        # win_pct por par (None si no hay resueltas win/loss).
        for d in por_par.values():
            resueltas = d["wins"] + d["losses"]
            d["win_pct"] = round(100.0 * d["wins"] / resueltas, 1) if resueltas else None

        wins = sum(d["wins"] for d in por_par.values())
        losses = sum(d["losses"] for d in por_par.values())
        nulas = sum(d["nulas"] for d in por_par.values())
        day_win_pct = round(100.0 * wins / (wins + losses), 1) if (wins + losses) else None

        # Mejor / peor par entre los que tienen al menos una resuelta. Desempate:
        # mejor -> mas wins; peor -> mas losses.
        medibles = {p: d for p, d in por_par.items() if d["win_pct"] is not None}
        best = max(medibles, key=lambda p: (medibles[p]["win_pct"],
                                            medibles[p]["wins"])) if medibles else None
        worst = min(medibles, key=lambda p: (medibles[p]["win_pct"],
                                             -medibles[p]["losses"])) if medibles else None

        # Modo recuperacion derivado de la DB (perdidas seguidas al cierre).
        en_recuperacion = sorted(
            p for p in por_par if self.store.trailing_losses(p) >= self.recovery_after)

        glob = self.store.win_rate()               # acumulado global (resueltas)
        acumulado = {"emitidas": self.store.emitted_count(),
                     "resueltas": glob["trades"], "win_pct": glob["win_pct"]}

        return {
            "bot_name": self.bot_name,
            "card_label": self.card_label,
            "total": total,
            "pares": sorted(por_par.keys()),
            "por_par": por_par,
            "wins": wins,
            "losses": losses,
            "nulas": nulas,
            "day_win_pct": day_win_pct,
            "best": best,
            "worst": worst,
            "recuperacion": en_recuperacion,
            "acumulado": acumulado,
        }

    # ------------------------------------------------------------- Markdown
    def to_markdown(self, stats: Dict[str, Any], fecha: str) -> str:
        """Resumen completo en Markdown (para guardar resumen_YYYY-MM-DD.md)."""
        h = [f"# Resumen diario — {stats['bot_name']} ({stats['card_label']})",
             f"Fecha: {fecha}  ·  cierre 00:00 UTC-4", ""]

        if stats["total"] == 0:
            h.append("Sin señales hoy.")
            h.append("")
            h.append(self._linea_acumulado(stats["acumulado"]))
            h.append("")
            h.append("⚠️ Demo · resumen educativo · el acierto no está garantizado")
            return "\n".join(h)

        h.append(f"**Señales totales:** {stats['total']}")
        h.append(f"**Pares operados:** {len(stats['pares'])} — {', '.join(stats['pares'])}")
        h.append("")
        h.append("## Resultados por par")
        h.append("| Par | Señales | WIN | LOSS | Empate | Pendiente | % |")
        h.append("|-----|--------:|----:|-----:|-------:|----------:|--:|")
        for p in stats["pares"]:
            d = stats["por_par"][p]
            pct = f"{d['win_pct']:.0f}%" if d["win_pct"] is not None else "—"
            h.append(f"| {p} | {d['signals']} | {d['wins']} | {d['losses']} | "
                     f"{d['ties']} | {d['pending']} | {pct} |")
        h.append("")

        acierto = (f"{stats['day_win_pct']:.0f}%" if stats["day_win_pct"] is not None
                   else "sin señales resueltas")
        h.append(f"**Acierto del día:** {acierto}  "
                 f"({stats['wins']}W / {stats['losses']}L)")
        if stats.get("nulas"):
            h.append(f"**Nulas (sin dato real, no cuentan):** {stats['nulas']}")
        h.append(f"**Mejor par:** {self._par_txt(stats, stats['best'])}")
        h.append(f"**Peor par:** {self._par_txt(stats, stats['worst'])}")

        if stats["recuperacion"]:
            h.append(f"**Modo recuperación:** SÍ — {', '.join(stats['recuperacion'])}")
        else:
            h.append("**Modo recuperación:** no")
        h.append("")
        h.append(self._linea_acumulado(stats["acumulado"]))
        h.append("")
        h.append("⚠️ Demo · resumen educativo · el acierto no está garantizado")
        return "\n".join(h)

    # ------------------------------------------------------------- Telegram
    def to_telegram(self, stats: Dict[str, Any], fecha: str) -> str:
        """Version corta para Telegram (Markdown). Mismos datos, sin la tabla."""
        if stats["total"] == 0:
            ac = stats["acumulado"]
            return (f"📋 *Resumen {fecha}* · {stats['bot_name']}\n"
                    f"Sin señales hoy.\n"
                    f"Acumulado: {ac['emitidas']} emitidas · acierto global "
                    f"{ac['win_pct']:.0f}% ({ac['resueltas']} resueltas)\n"
                    f"⚠️ Demo · resumen educativo · el acierto no está garantizado")

        acierto = (f"{stats['day_win_pct']:.0f}%" if stats["day_win_pct"] is not None
                   else "s/resueltas")
        recup = (", ".join(stats["recuperacion"]) if stats["recuperacion"] else "no")
        ac = stats["acumulado"]
        return (
            f"📋 *Resumen {fecha}* · {stats['bot_name']}\n"
            f"Señales: *{stats['total']}*  ·  Pares: {len(stats['pares'])}\n"
            f"Acierto del día: *{acierto}*  ({stats['wins']}W/{stats['losses']}L)"
            + (f"  ·  {stats['nulas']} nulas" if stats.get("nulas") else "") + "\n"
            f"Mejor: {self._par_txt(stats, stats['best'])}\n"
            f"Peor: {self._par_txt(stats, stats['worst'])}\n"
            f"Recuperación: {recup}\n"
            f"Acumulado: {ac['emitidas']} emitidas · global "
            f"{ac['win_pct']:.0f}% ({ac['resueltas']} resueltas)\n"
            f"⚠️ Demo · resumen educativo · el acierto no está garantizado")

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _par_txt(stats: Dict[str, Any], pair: Optional[str]) -> str:
        if pair is None:
            return "—"
        d = stats["por_par"][pair]
        return f"{pair} ({d['win_pct']:.0f}%, {d['wins']}W/{d['losses']}L)"

    @staticmethod
    def _linea_acumulado(ac: Dict[str, Any]) -> str:
        return (f"**Acumulado:** {ac['emitidas']} señales emitidas · "
                f"{ac['resueltas']} resueltas · acierto global {ac['win_pct']:.0f}%")
