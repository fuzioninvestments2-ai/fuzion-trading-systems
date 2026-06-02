"""Cache local de cadenas de opciones con TTL configurable."""
from __future__ import annotations
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

DEFAULT_TTL = 300       # 5 minutos
CACHE_DIR = Path("cache/options_chains")


class ChainCache:
    """Cache de cadenas de opciones en disco con TTL."""

    def __init__(self, ttl: int = DEFAULT_TTL, cache_dir: Path = CACHE_DIR):
        self.ttl = ttl
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[str, tuple[float, Any]] = {}

    def _key(self, symbol: str, expiry: Optional[str] = None) -> str:
        raw = f"{symbol}:{expiry or 'all'}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, symbol: str, expiry: Optional[str] = None) -> Optional[Any]:
        k = self._key(symbol, expiry)
        # memory first
        if k in self._memory:
            ts, data = self._memory[k]
            if time.time() - ts < self.ttl:
                return data
            del self._memory[k]
        # disk
        path = self.cache_dir / f"{k}.json"
        if path.exists():
            try:
                with open(path) as f:
                    entry = json.load(f)
                if time.time() - entry["ts"] < self.ttl:
                    self._memory[k] = (entry["ts"], entry["data"])
                    return entry["data"]
                path.unlink(missing_ok=True)
            except Exception:
                path.unlink(missing_ok=True)
        return None

    def set(self, symbol: str, data: Any, expiry: Optional[str] = None) -> None:
        k = self._key(symbol, expiry)
        ts = time.time()
        self._memory[k] = (ts, data)
        path = self.cache_dir / f"{k}.json"
        try:
            with open(path, "w") as f:
                json.dump({"ts": ts, "data": data}, f, default=str)
        except Exception:
            pass

    def invalidate(self, symbol: str, expiry: Optional[str] = None) -> None:
        k = self._key(symbol, expiry)
        self._memory.pop(k, None)
        path = self.cache_dir / f"{k}.json"
        path.unlink(missing_ok=True)

    def clear_all(self) -> None:
        self._memory.clear()
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
