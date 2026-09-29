"""Persistent operational logging for the platform."""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


class UTCFormatter(logging.Formatter):
    """Format operational timestamps in UTC."""

    converter = time.gmtime


def configure_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure console and rotating file handlers for sod_platform logs."""
    logger = logging.getLogger("sod_platform")
    logger.setLevel(level)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = UTCFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
