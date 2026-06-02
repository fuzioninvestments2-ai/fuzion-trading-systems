"""Logger estructurado JSON — 4 archivos rotativos, 10MB/5 backups."""
import json
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path


def _json_handler(log_file: str, max_bytes: int = 10_000_000, backup_count: int = 5):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    return handler


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str)


class FuzionLogger:
    def __init__(self, log_dir: str = "./logs"):
        self._log_dir = log_dir
        self.main = self._setup("fuzion.main", f"{log_dir}/main.log", logging.DEBUG)
        self.trades = self._setup("fuzion.trades", f"{log_dir}/trades.log", logging.INFO)
        self.regime = self._setup("fuzion.regime", f"{log_dir}/regime.log", logging.INFO)
        self.errors = self._setup("fuzion.errors", f"{log_dir}/errors.log", logging.ERROR)

    def _setup(self, name: str, path: str, level: int) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        if not logger.handlers:
            logger.addHandler(_json_handler(path))
        return logger

    def log_trade(self, **kwargs):
        self.trades.info("TRADE", extra=kwargs)

    def log_regime(self, regime: str, probability: float, symbol: str, **kwargs):
        self.regime.info("REGIME_UPDATE", extra={
            "regime": regime, "probability": probability,
            "symbol": symbol, **kwargs
        })

    def log_error(self, message: str, **kwargs):
        self.errors.error(message, extra=kwargs)

    def log_info(self, message: str, **kwargs):
        self.main.info(message, extra=kwargs)
