import logging
import sys
from collections.abc import MutableMapping
from typing import Any, Literal

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LogFormat = Literal["json", "text"]
STATUS_PREFIXES = {
    "pending": "[....]",
    "streaming": "[<-->]",
    "ok": "[ OK ]",
    "success": "[ OK ]",
    "fail": "[FAIL]",
    "failure": "[FAIL]",
    "retry": "[RETRY]",
}


def _add_status_prefix(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    status = event_dict.get("status")
    if isinstance(status, str):
        event_dict["prefix"] = STATUS_PREFIXES.get(status.lower(), "[....]")
    else:
        event_dict["prefix"] = "[....]"
    return event_dict


def _drop_status_prefix(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    event_dict.pop("prefix", None)
    return event_dict


def _render_text(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> str:
    del logger, method_name
    prefix = str(event_dict.pop("prefix", "[....]"))
    timestamp = str(event_dict.pop("timestamp", ""))
    level = str(event_dict.pop("level", "info")).upper()
    event = str(event_dict.pop("event", ""))
    event_dict.pop("logger", None)
    extras = " ".join(f"{key}={value!r}" for key, value in sorted(event_dict.items()))
    suffix = f" {extras}" if extras else ""
    return f"{prefix} {timestamp} {level:<7} {event}{suffix}"


def _build_renderer(log_format: LogFormat, *, colors: bool) -> Processor:
    del colors
    if log_format == "json":
        return structlog.processors.JSONRenderer()
    return _render_text


def setup_logging(
    *,
    log_format: LogFormat = "text",
    log_level: str = "INFO",
    colors: bool | None = None,
) -> None:
    resolved_colors = sys.stderr.isatty() if colors is None else colors
    renderer = _build_renderer(log_format, colors=resolved_colors)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_status_prefix,
    ]
    if log_format == "json":
        shared_processors.append(_drop_status_prefix)

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values: Any) -> structlog.stdlib.BoundLogger:
    values: MutableMapping[str, Any] = dict(initial_values)
    return structlog.get_logger(**values)
