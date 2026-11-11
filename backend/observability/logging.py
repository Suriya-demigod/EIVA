"""Structured, request-correlated console logging with sensitive-value redaction."""

import contextvars
import json
import logging
import re
import sys

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("eiva_request_id", default=None)

_SENSITIVE_PATTERNS = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), lambda match: match.group(1) + "[REDACTED]"),
    (
        re.compile(r"(?i)((?:groq[_-]?api[_-]?key|api[_-]?key|access[_-]?token|authorization)\s*[=:]\s*)[^\s,;]+"),
        lambda match: match.group(1) + "[REDACTED]",
    ),
    (re.compile(r"(?i)gsk_[A-Za-z0-9_-]{8,}"), lambda _: "[REDACTED]"),
)


def redact_sensitive_text(value: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = redact_sensitive_text(record.getMessage())
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": message,
        }
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging() -> None:
    logger = logging.getLogger("eiva")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
