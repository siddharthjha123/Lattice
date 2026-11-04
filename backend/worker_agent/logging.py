"""Structured local logs with worker-token redaction, including tracebacks."""

import json
import logging
from datetime import UTC, datetime


class RedactingFormatter(logging.Formatter):
    def __init__(self, token):
        super().__init__()
        self.token = token.get_secret_value()

    def format(self, record):
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage().replace(self.token, "[REDACTED]"),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info).replace(
                self.token, "[REDACTED]"
            )
        return json.dumps(data, ensure_ascii=False)


def configure_logging(token, stream=None):
    logger = logging.getLogger("worker_agent")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter(token))
    logger.handlers = [handler]
    # Protocol libraries must not emit credential-bearing handshake debug logs.
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
