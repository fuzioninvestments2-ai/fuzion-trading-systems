"""
dashboard/server.py (fuzion_fx) — APP DE TABLERO (sin terceros)
===============================================================
Servidor web LOCAL con la libreria estandar de Python (http.server): sirve la
interfaz (index.html) y una API JSON con el estado real del sistema, mas un
endpoint que dibuja el grafico de velas REAL de un par. Solo lectura.

    python fuzion_fx/dashboard/server.py       ->  http://127.0.0.1:8770

Por que stdlib: para NO depender de Flask/Streamlit (terceros). Todo el front va
en un solo index.html autocontenido (sin CDNs).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

FUZION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FUZION_ROOT not in sys.path:
    sys.path.insert(0, FUZION_ROOT)

from dashboard import panel_data                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8770


def _chart_png(pair: str, tf: int):
    """PNG del grafico de velas REAL del par+tf (o None si no hay datos)."""
    try:
        from collector.candle_store import CandleStore
        from telegram.chart import render_candles
        store = CandleStore(panel_data.DB_CANDLES)
        try:
            velas = store.get_real_candles(pair, tf, 60) or store.get_candles(pair, tf, 60)
        finally:
            store.close()
        if not velas:
            return None
        buf = render_candles(velas, f"{pair} · {tf}s (real)", "")
        return buf.getvalue() if buf else None
    except Exception:
        return None


def _matar(pid) -> None:
    """Termina un PID (multiplataforma). Best-effort."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                          capture_output=True)
        else:
            import signal
            os.kill(int(pid), signal.SIGTERM)
    except Exception:
        pass


def ejecutar_accion(accion: str, params: dict) -> dict:
    """
    Aplica una accion del panel y devuelve el resultado. Acciones seguras:
      pausar/reanudar -> pausa global de senales (no mata procesos).
      reiniciar       -> reinicia un servicio (colector por defecto): lo mata y el
                         vigilante lo revive; ademas se relanza al toque.
      escanear        -> no hace nada en el server (el cliente refresca el escaner).
    """
    from core import control
    if accion == "pausar":
        control.set_pausado(True)
        return {"ok": True, "pausado": True}
    if accion == "reanudar":
        control.set_pausado(False)
        return {"ok": True, "pausado": False}
    if accion == "reiniciar":
        from scripts.start_all import leer_pids, guardar_pids, lanzar_servicio
        from scripts.servicios import POR_NOMBRE
        nombre = params.get("nombre", "collector")
        if nombre not in POR_NOMBRE:
            return {"ok": False, "error": "servicio desconocido"}
        pids = leer_pids()
        if pids.get(nombre):
            _matar(pids[nombre])
        pids[nombre] = lanzar_servicio(nombre)
        guardar_pids(pids)
        return {"ok": True, "reiniciado": nombre, "pid": pids[nombre]}
    if accion == "telegram":
        bot = str(params.get("bot", ""))
        from dashboard.panel_data import BOTS
        if bot not in [b for b, _, _ in BOTS]:
            return {"ok": False, "error": "bot desconocido"}
        control.set_telegram(bot, bool(params.get("valor", True)))
        return {"ok": True, "bot": bot, "valor": bool(params.get("valor", True))}
    if accion.startswith("afiliado") or accion == "cobro":
        from core import afiliados
        if accion == "afiliado_alta":
            tfs = params.get("timeframes", []) or []
            aid = afiliados.alta(str(params.get("nombre", "")).strip() or "afiliado",
                                 str(params.get("chat_id", "")).strip(),
                                 [str(t) for t in tfs],
                                 float(params.get("fee", 0) or 0))
            return {"ok": True, "id": aid}
        if accion == "afiliado_pago":
            v = afiliados.marcar_pagado(int(params.get("id", 0)))
            return {"ok": v is not None, "vence": v}
        if accion == "afiliado_baja":
            afiliados.baja(int(params.get("id", 0)))
            return {"ok": True}
        if accion == "afiliado_tf":
            afiliados.set_timeframes(int(params.get("id", 0)),
                                     [str(t) for t in params.get("timeframes", [])])
            return {"ok": True}
        if accion == "cobro":
            afiliados.set_cobro(str(params.get("wallet", "")),
                                float(params.get("precio", 0) or 0),
                                str(params.get("moneda", "USDT")))
            return {"ok": True}
    if accion == "enviar_senal":
        from core import emisor
        pago = params.get("payout")
        return emisor.enviar_senal_manual(
            str(params.get("pair", "")), int(params.get("tf", 180) or 180),
            str(params.get("direccion", "CALL")), str(params.get("nota", "")),
            float(pago) if pago not in (None, "") else None)
    if accion == "escanear":
        return {"ok": True}
    return {"ok": False, "error": "accion desconocida"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:      # silencioso (no ensuciar consola)
        pass

    def do_POST(self) -> None:
        ruta = urlparse(self.path)
        if ruta.path != "/api/accion":
            self._send(404, b"no encontrado", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            cuerpo = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError):
            cuerpo = {}
        res = ejecutar_accion(str(cuerpo.get("accion", "")), cuerpo)
        self._send(200 if res.get("ok") else 400,
                   json.dumps(res).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        ruta = urlparse(self.path)
        if ruta.path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"index.html no encontrado", "text/plain")
            return
        if ruta.path == "/api/estado":
            body = json.dumps(panel_data.resumen_general()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/analisis":
            q = parse_qs(ruta.query)
            pair = q.get("pair", ["EUR/USD"])[0]
            try:
                tf = int(q.get("tf", ["180"])[0])
            except ValueError:
                tf = 180
            body = json.dumps(panel_data.analisis(pair, tf, 90)).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/candles":
            q = parse_qs(ruta.query)
            pair = q.get("pair", ["EUR/USD"])[0]
            try:
                tf = int(q.get("tf", ["180"])[0])
            except ValueError:
                tf = 180
            body = json.dumps(panel_data.candles_json(pair, tf, 90)).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/afiliados":
            body = json.dumps(panel_data.afiliados_panel()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/reporte":
            q = parse_qs(ruta.query)
            bot = q.get("bot", [None])[0] or None
            res = q.get("result", [None])[0] or None
            try:
                lim = int(q.get("limite", ["200"])[0])
            except ValueError:
                lim = 200
            body = json.dumps(panel_data.reporte_ordenes(bot, res, lim)).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/matriz":
            body = json.dumps(panel_data.escaner_matriz()).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/escaner":
            q = parse_qs(ruta.query)
            try:
                tf = int(q.get("tf", ["180"])[0])
            except ValueError:
                tf = 180
            body = json.dumps(panel_data.escaner(tf)).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if ruta.path == "/api/chart":
            q = parse_qs(ruta.query)
            pair = (q.get("pair", ["EUR/USD"])[0])
            try:
                tf = int(q.get("tf", ["180"])[0])
            except ValueError:
                tf = 180
            png = _chart_png(pair, tf)
            if png is None:
                self._send(404, b"sin datos", "text/plain")
            else:
                self._send(200, png, "image/png")
            return
        self._send(404, b"no encontrado", "text/plain")


def main() -> None:
    url = f"http://127.0.0.1:{PORT}"
    # --no-open: no abrir el navegador (lo usa el lanzador de ventana tipo app,
    # que abre el Chrome/Edge en modo aplicacion el mismo).
    abrir = "--no-open" not in sys.argv
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # Puerto ocupado = el tablero YA esta corriendo. No es error: se reusa.
        print(f"El tablero ya esta corriendo en {url}.")
        return
    print(f"Tablero Fuzion FX en {url}  (Ctrl+C para parar)")
    if abrir:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTablero detenido.")
        srv.shutdown()


if __name__ == "__main__":
    main()
