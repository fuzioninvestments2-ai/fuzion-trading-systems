"""
bot/dashboard_server.py
=======================
Sirve el dashboard en vivo (`dashboards/dashboard.html`) y su `estado.json` con el
servidor HTTP de la librería estándar (sin Flask ni dependencias). El bot escribe
`estado.json`; el navegador lo lee cada 3 s.

Uso:
  python -m bot.dashboard_server          # abre en http://localhost:8777
  python -m bot.dashboard_server --port 9000
"""
import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def _dir_dashboards():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "dashboards")


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=_dir_dashboards(), **k)

    def end_headers(self):
        # Sin caché: el estado cambia constantemente.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass                                   # silencioso


def servir(port=8777):
    carpeta = _dir_dashboards()
    os.makedirs(carpeta, exist_ok=True)
    idx = os.path.join(carpeta, "dashboard.html")
    if not os.path.exists(idx):
        print(f"Falta {idx}. ¿Hiciste git pull?")
        return
    srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    print(f"Dashboard en  http://localhost:{port}/dashboard.html")
    print("Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor del dashboard en vivo.")
    ap.add_argument("--port", type=int, default=8777)
    a = ap.parse_args()
    servir(a.port)
