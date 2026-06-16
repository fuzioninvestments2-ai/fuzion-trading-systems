"""
Análisis de noticias + sentimiento (la pata que TradingView NO puede hacer).

- Sentimiento con VADER (ligero, sin modelos pesados). Si está instalado
  `vaderSentiment` lo usa; si no, cae a un léxico financiero mínimo interno.
- Fuente de titulares: NewsAPI (https://newsapi.org) si hay NEWSAPI_KEY; si no,
  se le pueden pasar titulares a mano (analyze_headlines).

Devuelve un score [-1, +1] y un flag de "alto impacto" para que el ejecutor
(webhook/backend) pueda hacer override temporal de la estrategia:
p. ej. pausar entradas o cerrar si una noticia muy negativa golpea el activo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# Palabras clave por símbolo para filtrar titulares relevantes
SYMBOL_KEYWORDS = {
    "NVDA": ["nvidia", "nvda"], "TSLA": ["tesla", "musk", "tsla"],
    "AAPL": ["apple", "iphone", "aapl"], "AMZN": ["amazon", "amzn"],
    "META": ["meta", "facebook", "instagram"], "GOOGL": ["google", "alphabet"],
    "NFLX": ["netflix", "nflx"], "MSFT": ["microsoft", "msft"],
    "BTC-USD": ["bitcoin", "btc"], "ETH-USD": ["ethereum", "eth"],
}

# Léxico financiero mínimo (fallback si no hay vaderSentiment)
_POS = {"beat", "beats", "surge", "soar", "rally", "record", "upgrade", "growth",
        "profit", "strong", "bullish", "gain", "gains", "jump", "outperform", "win"}
_NEG = {"miss", "misses", "plunge", "crash", "fall", "drop", "downgrade", "loss",
        "weak", "bearish", "lawsuit", "probe", "ban", "cut", "warning", "fraud",
        "selloff", "slump", "recall", "default"}

# Umbral para considerar una noticia de "alto impacto"
HIGH_IMPACT_ABS = 0.6


@dataclass
class SentimentResult:
    symbol: str
    score: float = 0.0                 # -1..+1
    n_headlines: int = 0
    high_impact: bool = False
    direction: str = "neutral"         # bullish | bearish | neutral
    override: Optional[str] = None     # pause | close_risk | None
    headlines: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class NewsSentiment:
    def __init__(self, newsapi_key: Optional[str] = None):
        self.api_key = newsapi_key or os.getenv("NEWSAPI_KEY", "")
        self._vader = self._load_vader()

    @staticmethod
    def _load_vader():
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            return SentimentIntensityAnalyzer()
        except Exception:
            return None

    # ------------------------------------------------------------------
    def _score_text(self, text: str) -> float:
        if self._vader is not None:
            return self._vader.polarity_scores(text)["compound"]
        # fallback léxico
        words = [w.strip(".,!?:;\"'()").lower() for w in text.split()]
        pos = sum(1 for w in words if w in _POS)
        neg = sum(1 for w in words if w in _NEG)
        total = pos + neg
        return 0.0 if total == 0 else (pos - neg) / total

    # ------------------------------------------------------------------
    def analyze_headlines(self, symbol: str, headlines: List[str]) -> SentimentResult:
        if not headlines:
            return SentimentResult(symbol=symbol)
        scores = [self._score_text(h) for h in headlines]
        avg = sum(scores) / len(scores)
        peak = max(scores, key=abs) if scores else 0.0
        high_impact = abs(peak) >= HIGH_IMPACT_ABS
        direction = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
        override = None
        if high_impact:
            override = "close_risk" if peak < 0 else "pause"
        return SentimentResult(
            symbol=symbol, score=round(avg, 4), n_headlines=len(headlines),
            high_impact=high_impact, direction=direction, override=override,
            headlines=headlines[:10],
        )

    # ------------------------------------------------------------------
    def fetch_headlines(self, symbol: str, max_items: int = 20) -> List[str]:
        """Descarga titulares recientes de NewsAPI (requiere NEWSAPI_KEY)."""
        if not self.api_key:
            return []
        try:
            import httpx
        except Exception:
            return []
        query = " OR ".join(SYMBOL_KEYWORDS.get(symbol, [symbol.split("-")[0]]))
        url = "https://newsapi.org/v2/everything"
        params = {"q": query, "language": "en", "sortBy": "publishedAt",
                  "pageSize": max_items, "apiKey": self.api_key}
        try:
            r = httpx.get(url, params=params, timeout=10)
            r.raise_for_status()
            arts = r.json().get("articles", [])
            return [a.get("title", "") for a in arts if a.get("title")]
        except Exception:
            return []

    def analyze_symbol(self, symbol: str) -> SentimentResult:
        """Pipeline completo: descarga titulares y los analiza."""
        return self.analyze_headlines(symbol, self.fetch_headlines(symbol))

    def analyze_universe(self, symbols: List[str]) -> Dict[str, dict]:
        return {s: self.analyze_symbol(s).to_dict() for s in symbols}
