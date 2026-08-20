import logging
from collections.abc import MutableMapping
from typing import Any, Literal

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.observability.terminal import detect_terminal

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


DIM = "\x1b[2m"
RESET = "\x1b[0m"
# One colour per status prefix, since the prefix is what the eye lands on first when scanning a wall of requests.
PREFIX_COLOURS = {
    "[ OK ]": "\x1b[32m",
    "[FAIL]": "\x1b[31m",
    "[RETRY]": "\x1b[33m",
    "[<-->]": "\x1b[36m",
    "[....]": DIM,
}


def _paint(text: str, code: str, *, colors: bool) -> str:
    """Wrap `text` in one self-contained SGR span.

    Self-contained on purpose: each span carries its own reset and none of them nest. A nested span's reset would end the enclosing one too, which is how a line ends up half-coloured in a way nobody can reproduce from reading the code.
    """
    return f"{code}{text}{RESET}" if colors and text else text


def _render_text(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> str:
    """`[PREFIX] HH:MM:SS <message> <extras>`, the shape `DESIGN.md` records for console logs.

    No level column: the fixed-width prefix already says whether this went well, and repeating it in words pushes the part worth reading further right on every line.

    Extras are rendered plainly rather than with `repr`, so a path stays `/v1/messages` instead of becoming `'/v1/messages'`. They are the tail of the line by design — a request line puts what matters into the message itself and leaves only the incidental fields here.

    Colour is applied here rather than left to the caller because this is the only place that still knows which span is the prefix, which is the clock and which is the message. It is also where it was previously dropped: the resolved capability was passed in and immediately discarded, so a terminal that could take colour was told nothing about it.
    """
    del logger, method_name
    colors = bool(event_dict.pop("_colors", False))
    prefix = str(event_dict.pop("prefix", "[....]"))
    timestamp = str(event_dict.pop("timestamp", ""))
    event = str(event_dict.pop("event", ""))
    event_dict.pop("logger", None)
    event_dict.pop("level", None)
    # The prefix is this field, rendered. Printing it again at the end of the line says the same thing twice and pushes the message left of a column of `status=ok`.
    event_dict.pop("status", None)
    extras = " ".join(f"{key}={value}" for key, value in sorted(event_dict.items()))
    suffix = f" {_paint(extras, DIM, colors=colors)}" if extras else ""
    painted_prefix = _paint(prefix, PREFIX_COLOURS.get(prefix, DIM), colors=colors)
    return f"{painted_prefix} {_paint(timestamp, DIM, colors=colors)} {event}{suffix}"


def _build_renderer(log_format: LogFormat, *, colors: bool) -> Processor:
    if log_format == "json":
        return structlog.processors.JSONRenderer()

    def render(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> str:
        event_dict["_colors"] = colors
        return _render_text(logger, method_name, event_dict)

    return render


def setup_logging(
    *,
    log_format: LogFormat = "text",
    log_level: str = "INFO",
    colors: bool | None = None,
) -> None:
    # One detector for the whole process. Asking `isatty()` here as well would be a second answer to the same question, free to disagree with the one the footer uses — and a log stream that colours itself while the footer has decided the terminal cannot take colour is exactly the kind of split nobody thinks to look for.
    resolved_colors = detect_terminal().color if colors is None else colors
    renderer = _build_renderer(log_format, colors=resolved_colors)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        # Wall-clock time of day for the console, an absolute UTC instant for JSON. A person watching a terminal is placing the line against the request they just made; a log shipper is correlating it with another machine, and `HH:MM:SS` cannot survive that.
        structlog.processors.TimeStamper(fmt="iso", utc=True)
        if log_format == "json"
        else structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
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

    # Libraries that narrate their own progress at INFO. This process already says when it is listening and what each request did, so leaving these on means every one of those lines arrives twice — once in our words and once in theirs — and `httpx` additionally announces every upstream call, which on a proxy is the same event as the request line right below it. Raised to WARNING rather than silenced: when one of them has something to say that is not routine, it still gets through.
    for noisy in ("uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "", **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """A bound logger, optionally under a named stdlib logger.

    The name matters beyond tidiness: it is what lets a caller — a test, a filter, a log shipper — select this process's own lines out of a stream that also carries `httpx` and `uvicorn`. Selecting on message content instead looks equivalent until a third-party line happens to contain the same substring, which `httpx` does for every upstream call it narrates.
    """
    values: MutableMapping[str, Any] = dict(initial_values)
    if name:
        return structlog.get_logger(name, **values)
    return structlog.get_logger(**values)
