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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:      # silencioso (no ensuciar consola)
        pass

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
