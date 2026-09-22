"""The site's logging: JSON lines on stderr, configured in one place.

Every record is one JSON object, so `journalctl -u golf-site -o cat | jq` reads the log.
A record carries the id of the request it happened in (`request_id`), which the timing
middleware mints and also returns as the `X-Request-Id` header, so a log line, a `timings`
row and a player's report of a failure all name the same request.

`log_config` is handed to uvicorn as its `log_config`, rather than applied here: uvicorn
applies it in each worker it starts, including the child process `--reload` spawns, where
nothing `golf-site` ran itself survives. Configuring the root logger from `create_app`
instead would also have every test's app fight over it.

uvicorn's access log is off. Caddy logs every request with the duration the client
actually experienced (`deploy/Caddyfile`); what the app adds is a line for the notable
ones, with the phases the proxy cannot see.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

DEFAULT_LEVEL = "INFO"

#: the current request's id, set by the timing middleware; empty outside a request
request_id: ContextVar[str] = ContextVar("request_id", default="")

#: what `logging` puts on every record itself, so the rest came from a caller's `extra=`
_STANDARD = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "request_id",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _timestamp(created: float) -> str:
    """The record's time, UTC to the millisecond."""
    stamp = datetime.fromtimestamp(created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return f"{stamp[:-3]}Z"


class JsonFormatter(logging.Formatter):
    """One JSON object per record: the fixed fields, then whatever `extra=` carried."""

    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "ts": _timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        }
        fields.update(
            (name, value)
            for name, value in record.__dict__.items()
            if name not in _STANDARD and not name.startswith("_")
        )
        if record.exc_info:
            fields["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            fields["stack"] = self.formatStack(record.stack_info)
        # A value logging cannot serialize is worth its repr, never a lost record.
        return json.dumps(fields, default=repr)


class RequestIdFilter(logging.Filter):
    """Stamp every record with the request it happened in, or nothing outside one."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def known_level(level: str) -> bool:
    return level.upper() in logging.getLevelNamesMapping()


def log_config(level: str = DEFAULT_LEVEL) -> dict[str, Any]:
    """The `logging.config.dictConfig` dictionary uvicorn applies in each worker."""
    return {
        "version": 1,
        # server.submissions and the rest hold module-level loggers made at import time.
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": RequestIdFilter}},
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "json",
                "filters": ["request_id"],
            }
        },
        "root": {"handlers": ["stderr"], "level": level.upper()},
        "loggers": {
            # uvicorn's own records go out through the root handler like any other.
            "uvicorn": {"handlers": [], "propagate": True},
            "uvicorn.error": {"handlers": [], "propagate": True},
            "uvicorn.access": {"handlers": [], "propagate": False},
        },
    }
