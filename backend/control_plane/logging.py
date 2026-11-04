"""Structured service logs with configured secrets excluded from output."""

import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit


def redact_message(message, config):
    """Preserve diagnostic text while removing service/URL/token credentials."""
    result = str(message)
    secrets = [
        config.ADMIN_TOKEN.get_secret_value(),
        config.SECRET_KEY,
        config.REGISTRY_PASSWORD.get_secret_value(),
        config.DATABASE_URL,
    ]
    try:
        password = urlsplit(config.DATABASE_URL).password
        if password:
            secrets.extend((password, unquote(password)))
    except ValueError:
        pass
    for value in sorted({value for value in secrets if value}, key=len, reverse=True):
        result = result.replace(value, "[REDACTED]")
    result = re.sub(
        r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", result, flags=re.IGNORECASE
    )
    result = re.sub(
        r"\b(Bearer|Basic)\s+[A-Za-z0-9_./+=-]+",
        r"\1 [REDACTED]",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"([?&](?:access_token|token|password|auth|signature|x-amz-signature|x-amz-credential|x-amz-security-token)=)[^&\s\"<>]+",
        r"\1[REDACTED]",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AVNS_[A-Za-z0-9_-]{15,})",
        "[REDACTED]",
        result,
    )
    return result


class ServiceFormatter(logging.Formatter):
    def __init__(self, config):
        super().__init__()
        self.config = config

    def format(self, record):
        message = redact_message(record.getMessage(), self.config)
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": message,
        }
        if record.exc_info:
            data["exception_type"] = record.exc_info[0].__name__
        return json.dumps(data, ensure_ascii=False)


def configure_logging(config, stream=None):
    logger = logging.getLogger("control_plane")
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ServiceFormatter(config))
    for previous in logger.handlers:
        previous.close()
    logger.handlers = [handler]
    for name in ("websockets", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
