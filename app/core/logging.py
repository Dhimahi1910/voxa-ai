"""Structured JSON logging with secret redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),
    re.compile(r"(vp_(?:live|test)_)[A-Za-z0-9]+"),
    re.compile(r"((?:api[_-]?key|secret|token|password|key)=)[^&\s\"']+", re.I),
]
_SENSITIVE_KEYS = ("key", "secret", "token", "password", "authorization", "credential")
_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def redact(text: str) -> str:
    for p in _SECRET_PATTERNS:
        text = p.sub(r"\1***", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k in _STD:
                continue
            out[k] = "***" if any(s in k.lower() for s in _SENSITIVE_KEYS) else (redact(v) if isinstance(v, str) else v)
        if record.exc_info:
            out["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(out, default=str)


def setup_logging(level: str = "INFO") -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level.upper())
    # httpx logs full URLs at INFO, which can contain tokens
    logging.getLogger("httpx").setLevel(logging.WARNING)
