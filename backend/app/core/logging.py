"""Logging setup. Logs to console and to monitoring/logs/application.log.

No sensitive data (file contents, secrets, unnecessary personal information)
should ever be logged. Filenames are safe (original name is metadata only).
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "monitoring" / "logs"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("certverify")
    if logger.handlers:
        return

    logger.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))

    file_handler = RotatingFileHandler(
        LOG_DIR / "application.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    logger.addHandler(console)
    logger.addHandler(file_handler)

    # Suppress noisy third-party logs unless configured
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"certverify.{name}")