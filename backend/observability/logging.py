"""Minimal JSON-friendly console logging for model telemetry."""

import logging
import sys


def configure_logging() -> None:
    logger = logging.getLogger("eiva")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
