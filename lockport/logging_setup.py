"""Centralized logging configuration for LockPort."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import DEFAULT_CONFIG


def configure_logging(*, force_console: bool | None = None) -> logging.Logger:
    """Configure root logger for the LockPort service."""
    log_file = DEFAULT_CONFIG.log_location
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(threadName)s - %(message)s"
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger("lockport")
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        logger.addHandler(handler)

    console_pref = force_console
    if console_pref is None:
        console_pref = os.environ.get("LOCKPORT_CONSOLE_LOG", "0") not in {"0", ""}
    if console_pref and not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
