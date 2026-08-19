"""The per-request console lines.

`DESIGN.md` fixes the frame: `[PREFIX] HH:MM:SS METHOD /path ...`, with the fixed-width prefix and the timestamp supplied by the structlog processor chain. What this module builds is the part after them.

The field order follows `copilot-api-js`, whose real rendered lines look like `[ OK ] 14:25:36 200 anthropic/claude-opus-4-8 1.2s ↑1.0k+8.0k+1.0k ↻80% ↓456 end_turn`. Two things there are deliberate rather than incidental, and both are kept: a **successful** line collapses method and path into `<inbound-format>/<model>`, because once a request has worked, which model answered is the thing worth reading and the route is noise; a **failed** one keeps `METHOD /path`, because that is what has to be reproduced.

Bytes and tokens both use `↑`/`↓` and are told apart by unit, again as upstream does: bytes carry `B`/`KB`/`MB`, token counts are bare with a `k`/`m` suffix. Every field is dropped when it has nothing to say, so the line grows only with what actually happened.

Kept pure and separate from the emitting call so a line can be asserted without a logger, a terminal or a served request.
"""

from dataclasses import dataclass, field
from typing import Any

from app.observability.footer import format_bytes, format_duration


@dataclass(frozen=True, slots=True)
class RequestLine:
    """Everything one request contributes to its own log line.

    `model` empty means routing never resolved one — a rejected body, an unknown model. It is then left out rather than printed as a placeholder, which is what `DESIGN.md` means by not showing model or tokens for a non-model request.

    `bytes_in` / `bytes_out` are wire bytes in each direction; `usage` is the upstream's own token accounting, keyed as Anthropic reports it. The two are separate facts and a request can have either without the other — a rejected body has bytes and no tokens, a cached hit has tokens and almost no bytes.
    """

    method: str
    path: str
    inbound_format: str = ""
    requested_model: str = ""
    model: str = ""
    status_code: int | None = None
    duration_s: float | None = None
    bytes_in: int | None = None
    bytes_out: int | None = None
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stop_reason: str = ""
    attempts: int = 1
    detail: str = ""


def format_count(value: int) -> str:
    """Compact token counts. Bare of any byte unit, which is what tells a token column from a byte one."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def format_tokens(usage: dict[str, Any], *, unicode: bool = True) -> str:
    """`↑<input>[+<cache-read>][+<cache-write>][ ↻<hit>%] ↓<output>`, or empty when nothing was reported.

    The cache breakdown is additive on the input side because that is what the numbers are: reading from cache and writing to it are both ways of supplying input. The hit rate is shown only when there was cache activity, since `↻0%` on every uncached request is a column of noise.

    `↓output` is rendered whenever it was measured, `0` included — a request that produced no output tokens is a real and interesting outcome, and omitting it would make that indistinguishable from an endpoint that does not count output at all.
    """

    def read(key: str) -> int:
        value = usage.get(key)
        return value if isinstance(value, int) else 0

    if not usage:
        return ""
    up, down = ("↑", "↓") if unicode else (">", "<")
    input_tokens = read("input_tokens")
    cache_read = read("cache_read_input_tokens")
    cache_write = read("cache_creation_input_tokens")

    parts = [f"{up}{format_count(input_tokens)}"]
    if cache_read:
        parts[0] += f"+{format_count(cache_read)}"
    if cache_write:
        parts[0] += f"+{format_count(cache_write)}"

    supplied = input_tokens + cache_read + cache_write
    if cache_read or cache_write:
        # Both rates, as upstream shows them: what came out of cache, and what went into it on this request. `+new%` is what tells a warm prompt apart from one that just paid to be cached, which read alone cannot.
        rate = "↻" if unicode else "cache "
        hit = round(100 * cache_read / supplied) if supplied else 0
        new = round(100 * cache_write / supplied) if supplied else 0
        parts.append(f"{rate}{hit}%+{new}%" if cache_write else f"{rate}{hit}%")

    if "output_tokens" in usage:
        parts.append(f"{down}{format_count(read('output_tokens'))}")
    return " ".join(parts)


def _subject(line: RequestLine, *, succeeded: bool) -> list[str]:
    """Who the request was for: the model when it worked, the route when it did not.

    A mapped model is shown as `asked → answered`, because a line reporting only the resolved name hides the mapping — and a mapping doing something unintended is invisible in exactly the request where it matters.
    """
    named = line.model
    if line.requested_model and line.model and line.requested_model != line.model:
        named = f"{line.requested_model} → {line.model}"

    if succeeded and named:
        return [f"{line.inbound_format}/{named}" if line.inbound_format else named]
    parts = [line.method, line.path]
    if named:
        parts.append(named)
    return parts


def format_arrival_line(line: RequestLine) -> str:
    """`METHOD /path [model]` — what is known when the request shows up and nothing more."""
    parts = [line.method, line.path]
    if line.model:
        parts.append(line.model)
    return " ".join(parts)


def format_completion_line(line: RequestLine, *, unicode: bool = True) -> str:
    """The message body for a finished request.

    Ordered status, subject, duration, wire bytes, tokens, stop reason, retries, detail — narrowing from how it went, to what it cost, to why it ended. Every field after the subject is omitted when it has nothing to say, so a bare rejection and a full streamed answer share one column order instead of drifting into two formats.
    """
    succeeded = line.status_code is not None and line.status_code < 400
    up, down = ("↑", "↓") if unicode else (">", "<")

    parts: list[str] = []
    if line.status_code is not None:
        parts.append(str(line.status_code))
    parts.extend(_subject(line, succeeded=succeeded))
    if line.duration_s is not None:
        parts.append(format_duration(line.duration_s))

    # Wire bytes, one field for both directions so they read as a pair rather than as two unrelated numbers.
    wire = [f"{up}{format_bytes(line.bytes_in)}" if line.bytes_in is not None else "", f"{down}{format_bytes(line.bytes_out)}" if line.bytes_out is not None else ""]
    parts.extend(part for part in wire if part)

    tokens = format_tokens(line.usage, unicode=unicode)
    if tokens:
        parts.append(tokens)
    if line.stop_reason:
        parts.append(line.stop_reason)
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
