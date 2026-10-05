from __future__ import annotations

import logging
import sys
from typing import Any

_SENSITIVE_KEYS = {
    "api_key", "password", "token", "access_token", "refresh_token",
    "credentials", "secret", "authorization", "hashed_password",
}

_CONFIGURED = False


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__.keys()):
            if key.lower() in _SENSITIVE_KEYS:
                record.__dict__[key] = "***REDACTED***"
        return True


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger("aura")
    root.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    handler.addFilter(_RedactingFilter())
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(f"aura.{name}")


def safe_extra(**kwargs: Any) -> dict:
    return dict(kwargs)
