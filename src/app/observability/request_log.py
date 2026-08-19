"""The per-request console lines.

`DESIGN.md` fixes the frame: `[PREFIX] HH:MM:SS METHOD /path ...`, with the fixed-width prefix and the timestamp supplied by the structlog processor chain. What this module builds is the part after them.

The field order follows `copilot-api-js`, whose real rendered lines are `[ OK ] 14:25:36 200 anthropic/claude-opus-4-8 3.0s ↓12.1KB` and `[FAIL] 14:25:36 429 POST /v1/messages gpt-5 1.0s: rate_limited`. Two things there are deliberate rather than incidental, and both are kept: a **successful** line collapses method and path into `<inbound-format>/<model>`, because once a request has worked, which model answered is the thing worth reading and the route is noise; a **failed** one keeps `METHOD /path`, because that is what has to be reproduced.

Kept pure and separate from the emitting call so a line can be asserted without a logger, a terminal or a served request.
"""

from dataclasses import dataclass

from app.observability.footer import format_bytes, format_duration


@dataclass(frozen=True, slots=True)
class RequestLine:
    """Everything one request contributes to its own log line.

    `model` empty means routing never resolved one — a rejected body, an unknown model. It is then left out rather than printed as a placeholder, which is what `DESIGN.md` means by not showing model or tokens for a non-model request.
    """

    method: str
    path: str
    inbound_format: str = ""
    model: str = ""
    status_code: int | None = None
    duration_s: float | None = None
    bytes_out: int | None = None
    attempts: int = 1
    detail: str = ""


def format_arrival_line(line: RequestLine) -> str:
    """`METHOD /path [model]` — what is known when the request shows up and nothing more."""
    parts = [line.method, line.path]
    if line.model:
        parts.append(line.model)
    return " ".join(parts)


def format_completion_line(line: RequestLine, *, unicode: bool = True) -> str:
    """The message body for a finished request.

    Ordered status, subject, duration, bytes, retries, detail — narrowing from how it went to what it cost. Every field after the subject is omitted when it has nothing to say, so a bare rejection and a full streamed answer share one column order instead of drifting into two formats.
    """
    succeeded = line.status_code is not None and line.status_code < 400
    parts: list[str] = []
    if line.status_code is not None:
        parts.append(str(line.status_code))

    if succeeded and line.model:
        parts.append(f"{line.inbound_format}/{line.model}" if line.inbound_format else line.model)
    else:
        parts.extend([line.method, line.path])
        if line.model:
            parts.append(line.model)

    if line.duration_s is not None:
        parts.append(format_duration(line.duration_s))
    if line.bytes_out is not None:
        # Present only once something has streamed back. Its absence says "nothing came back", which is a different fact from `↓0B`.
        parts.append(f"{'↓' if unicode else '<'}{format_bytes(line.bytes_out)}")
    if line.attempts > 1:
        # Named on the line that reports the outcome, where the count is final. A retry still in progress is the footer's job.
        parts.append(f"retries={line.attempts - 1}")

    rendered = " ".join(parts)
    # A colon rather than a space before the reason, matching the upstream shape and giving the eye somewhere to stop on a line that is otherwise all fields.
    return f"{rendered}: {line.detail}" if line.detail else rendered


def status_for(status_code: int | None, *, failed: bool) -> str:
    """The `status` field the prefix processor turns into `[ OK ]` or `[FAIL]`.

    Driven by whether the request produced a usable response rather than by the exception type, so an upstream 500 delivered intact and a transport error that produced nothing both read as failures — which is what the person watching cares about.
    """
    if failed or status_code is None:
        return "fail"
    return "ok" if status_code < 400 else "fail"
