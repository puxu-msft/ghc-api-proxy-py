import logging
from collections.abc import MutableMapping
from typing import Any, Literal

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.observability.terminal import CYAN, DIM, GREEN, RED, YELLOW, detect_terminal, paint

LogFormat = Literal["json", "text"]
STATUS_PREFIXES = {
    "pending": "[....]",
    "streaming": "[<-->]",
    # Every line of a shutdown sequence carries this one, whichever rung it reports. They are the same kind of event and giving them different prefixes by severity said, wrongly, that one of them had succeeded and another was streaming. Severity is the closing line's job.
    "draining": "[DRIN]",
    "ok": "[ OK ]",
    "success": "[ OK ]",
    "fail": "[FAIL]",
    "failure": "[FAIL]",
    # A request nobody was left to receive. Its own tier because the alternatives both say something untrue: `[ OK ]` is what a client that pressed Esc used to get, which is indistinguishable from an answer that arrived, and `[FAIL]` puts a cancelled turn in the same colour as an upstream that tore — on a proxy fronting an interactive client, cancels are routine and would drown the failures that are not.
    "gone": "[GONE]",
    # Four characters inside the brackets, like every other prefix here. Spelt out because the obvious spelling is one too wide: the column these open is fixed, and a seven-character prefix shifts every field on that one line out of step with the wall of lines above it.
    "retry": "[RETY]",
}
# The fallback for a record that carries no `status`, which is every record from a library: asyncio, httpx, httpcore, uvicorn, sqlite. They have no way to set one, so they all landed on `[....]` — the same prefix, and the same dimmed styling, as a line saying a request has just started. `_render_text` then drops `level`, so in text mode a third-party ERROR was not merely hard to spot, it was unfindable: the word never reached the output for anyone to grep. That is the opposite of what raising those loggers to WARNING below is for.
LEVEL_PREFIXES = {
    "critical": "[FAIL]",
    "error": "[FAIL]",
    "exception": "[FAIL]",
    "warning": "[WARN]",
    "warn": "[WARN]",
}


def _add_status_prefix(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger
    status = event_dict.get("status")
    if isinstance(status, str):
        event_dict["prefix"] = STATUS_PREFIXES.get(status.lower(), "[....]")
        return event_dict
    # `status` first, so nothing this project reports changes shape: an outcome it named itself outranks the severity it happened to log at. `level` is set by `add_log_level` earlier in this same chain and is present for library records too; `method_name` is the fallback for a caller that reaches this processor without it.
    level = event_dict.get("level")
    severity = level if isinstance(level, str) else method_name
    event_dict["prefix"] = LEVEL_PREFIXES.get(severity.lower(), "[....]")
    return event_dict


def _drop_status_prefix(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    event_dict.pop("prefix", None)
    return event_dict


PENDING = "[....]"
# One colour per status prefix, since the prefix is what the eye lands on first when scanning a wall of requests.
PREFIX_COLOURS = {
    "[ OK ]": GREEN,
    "[FAIL]": RED,
    # Between the two it sits between: something did not finish, and nothing is wrong with the proxy or with upstream.
    "[GONE]": YELLOW,
    "[WARN]": YELLOW,
    "[RETY]": YELLOW,
    "[<-->]": CYAN,
    "[DRIN]": YELLOW,
    PENDING: DIM,
}


def _render_text(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> str:
    """`[PREFIX] HH:MM:SS <message> <extras>`, the console log shape this project has kept — `app.observability.request_log` records where the frame came from.

    No level column: the fixed-width prefix already says whether this went well, and repeating it in words pushes the part worth reading further right on every line.

    Extras are rendered plainly rather than with `repr`, so a path stays `/v1/messages` instead of becoming `'/v1/messages'`. They are the tail of the line by design — a request line puts what matters into the message itself and leaves only the incidental fields here.

    Colour is applied here rather than left to the caller because this is the only place that still knows which span is the prefix, which is the clock and which is the message. It is also where it was previously dropped: the resolved capability was passed in and immediately discarded, so a terminal that could take colour was told nothing about it.

    The message itself arrives already coloured when it is a request line — that builder knows which field is a model and which is a duration, and this one does not. The exception is a pending line, which is dimmed whole: it says only that a request has started, and it should not compete with the outcome lines around it.
    """
    del logger, method_name
    colors = bool(event_dict.pop("_colors", False))
    prefix = str(event_dict.pop("prefix", PENDING))
    timestamp = str(event_dict.pop("timestamp", ""))
    event = str(event_dict.pop("event", ""))
    event_dict.pop("logger", None)
    event_dict.pop("level", None)
    # The prefix is this field, rendered. Printing it again at the end of the line says the same thing twice and pushes the message left of a column of `status=ok`.
    event_dict.pop("status", None)
    # Taken out of the extras and given its own lines. A traceback is many lines of text that the reader works through top to bottom, and rendering it as one more `key=value` at the tail puts it on the same line as the message — which is how it stayed unread.
    traceback = event_dict.pop("exception", None)
    extras = " ".join(f"{key}={value}" for key, value in sorted(event_dict.items()))
    suffix = f" {paint(extras, DIM, color=colors)}" if extras else ""
    body = paint(event, DIM, color=colors) if prefix == PENDING else event
    painted_prefix = paint(prefix, PREFIX_COLOURS.get(prefix, DIM), color=colors)
    trace = f"\n{traceback}" if traceback else ""
    return f"{painted_prefix} {paint(timestamp, DIM, color=colors)} {body}{suffix}{trace}"


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
        structlog.stdlib.PositionalArgumentsFormatter(),
        # Wall-clock time of day for the console, an absolute UTC instant for JSON. A person watching a terminal is placing the line against the request they just made; a log shipper is correlating it with another machine, and `HH:MM:SS` cannot survive that.
        structlog.processors.TimeStamper(fmt="iso", utc=True)
        if log_format == "json"
        else structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        # `ProcessorFormatter` does not format exceptions on its own, and without this every `exc_info` reached the renderer as a raw tuple and was printed as one more extra: `exc_info=(<class 'ValueError'>, ValueError('...'), <traceback object at 0x7f...>)`, with `exc_info=True` degrading further to the literal `True`. So no exception this process ever logged carried a stack — including asyncio's own handler, which is how `StopAsyncIteration exception in shielded future` arrived with nothing to trace it by.
        # Listed here rather than in the formatter's own chain because this list is both the `foreign_pre_chain` and what `structlog.configure` runs, so one entry covers stdlib records and structlog's own. It has to run at logging time either way: `exc_info=True` is resolved with `sys.exc_info()`, which only answers inside the `except` block that logged it.
        structlog.processors.format_exc_info,
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
