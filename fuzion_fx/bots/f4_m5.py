"""
bots/f4_m5.py (fuzion_fx) — Proceso INDEPENDIENTE del bot f4_m5.
Se arranca con:  python fuzion_fx/bots/f4_m5.py
Sin hilos, sin matrix: es su propio proceso, con su propia sqlite.
"""

import os
import sys

# Pone fuzion_fx/ en el path para que 'from core...', 'from indicators...' anden.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.base_bot import BaseBot          # noqa: E402


def main() -> None:
    # Con feed/notifier por defecto: price_feed placeholder + Telegram de .env.
    BaseBot("f4_m5").run()


if __name__ == "__main__":
    main()
