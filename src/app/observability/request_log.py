"""The per-request console lines.

`DESIGN.md` fixes the frame: `[PREFIX] HH:MM:SS METHOD /path ...`, with the fixed-width prefix and the timestamp supplied by the structlog processor chain. What this module builds is the part after them.

The field order follows `copilot-api-js`, whose real rendered lines look like `[ OK ] 14:25:36 200 anthropic/claude-opus-4-8 1.2s ↑1.0k+8.0k+1.0k ↻80% ↓456 end_turn`. Two things there are deliberate rather than incidental, and both are kept: a **successful** line collapses method and path into `<inbound-format>/<model>`, because once a request has worked, which model answered is the thing worth reading and the route is noise; a **failed** one keeps `METHOD /path`, because that is what has to be reproduced.

Bytes and tokens both use `↑`/`↓` and are told apart by unit, again as upstream does: bytes carry `B`/`KB`/`MB`, token counts are bare with a `k`/`m` suffix. Every field is dropped when it has nothing to say, so the line grows only with what actually happened.

Kept pure and separate from the emitting call so a line can be asserted without a logger, a terminal or a served request.
"""

from dataclasses import dataclass, field
from typing import Any

from app.observability.footer import format_bytes, format_duration
from app.observability.terminal import (
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    RED,
    WHITE,
    YELLOW,
    cache_hit_colour,
    duration_colour,
    paint,
    volume_colour,
)
from app.pipeline.delivery.assembler import ReplyDialect

# What to call the same two things under each upstream, abbreviated to fit a line. Held here, in the layer that renders, because which word to print is a display decision; what happened is the record's business and it says only which upstream described it.
# `tool_use` is the Anthropic stop reason the Responses assembler synthesises for the client's benefit. Recognised by name so the line can put back what upstream actually sent.
TOOL_USE_REASON = "tool_use"
REASONING_WORD = {ReplyDialect.ANTHROPIC: "think", ReplyDialect.RESPONSES: "reason"}
TOOL_WORD = {ReplyDialect.ANTHROPIC: TOOL_USE_REASON, ReplyDialect.RESPONSES: "function_call"}

# Where a reply stops being ordinary, stated on the scale the reader sees rather than in raw units: kilobytes for wire bytes, thousands for token counts.
NOTABLE_KB, HEAVY_KB = 10.0, 100.0
NOTABLE_K_TOKENS, HEAVY_K_TOKENS = 1.0, 10.0

# How the turn ended, as a ladder rather than a flag. Every one of these is terminal, so a single colour would say only "it stopped" — which the presence of the field already says. What the reader wants is how much of a problem the ending was.
# Green has to keep meaning "nothing to look at here", so a reply cut off at the token limit cannot share it: truncation is the one thing about that line worth seeing. A refusal goes further still — nothing was delivered and the turn cannot simply be resumed — which is why it sits at the same level as a failed status rather than one below.
# `tool_use` is absent on purpose. It does end the model's reply, but it is the one reason that says the *work* is not over: the caller is expected to run the tools and come back, so painting it as an ending would put a full stop on the most common midpoint.
# A closed whitelist rather than a rule. An unrecognised reason is left uncoloured, because there is no way to tell from its name whether it is good news or bad, and colouring it either way would assert something this code does not know.
REASON_COLOURS = {
    "end_turn": GREEN,
    "stop_sequence": GREEN,
    "max_tokens": YELLOW,
    "refusal": RED,
}

# Tools whose presence means the turn is waiting on a person rather than on a machine. Worth picking out of an otherwise quiet list: it is the one entry that will not resolve on its own.
ATTENTION_TOOLS = frozenset({"AskUserQuestion"})


def http_label(version: str | None, *, websocket: bool = False) -> str:
    """`H1` / `H2` / `WS` — which protocol carried this leg.

    Short because it sits at the front of every line and its job is to be noticed only when it is not what was expected. `HTTP/1` and `HTTP/1.1` collapse to one label: the distinction has no bearing on anything this proxy does, while 1 versus 2 changes multiplexing and framing. A WebSocket is HTTP/1.1 underneath, but calling it `H1` would hide the one thing about it that matters.
    """
    if websocket:
        return "WS"
    if not version:
        return ""
    normalised = version.removeprefix("HTTP/")
    if normalised.startswith("2"):
        return "H2"
    if normalised.startswith("1"):
        return "H1"
    return normalised


def format_protocols(client: str, upstream: str) -> str:
    """`<client>/<upstream>`, the two legs this proxy sits between, in that order.

    Ordered as the request travels. Either side may be unknown — a request rejected before it reached upstream has no second leg — and the pair then degrades to whichever half is known rather than printing a placeholder for the other.
    """
    if client and upstream:
        return f"{client}/{upstream}"
    return client or upstream


@dataclass(frozen=True, slots=True)
class RequestLine:
    """Everything one request contributes to its own log line.

    `model` empty means routing never resolved one — a rejected body, an unknown model. It is then left out rather than printed as a placeholder, which is what `DESIGN.md` means by not showing model or tokens for a non-model request.

    `bytes_in` / `bytes_out` are wire bytes in each direction; `usage` is the upstream's own token accounting, keyed as Anthropic reports it. The two are separate facts and a request can have either without the other — a rejected body has bytes and no tokens, a cached hit has tokens and almost no bytes.
    """

    method: str
    path: str
    inbound_format: str = ""
    client_protocol: str = ""
    upstream_protocol: str = ""
    requested_model: str = ""
    model: str = ""
    status_code: int | None = None
    duration_s: float | None = None
    bytes_in: int | None = None
    bytes_out: int | None = None
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stop_reason: str = ""
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    # Whose words to use for the reasoning and tool-call fields. See `ReplyDialect`; it travels with the reply summary the line is built from.
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    attempts: int = 1
    detail: str = ""


def format_thinking(kinds: tuple[str, ...], dialect: ReplyDialect = ReplyDialect.ANTHROPIC) -> str:
    """`think(enc:1)` / `reason(enc:1,txt:2)` — how much reasoning came back, and of which sort.

    The leading word is abbreviated from each upstream's own vocabulary: Anthropic sends `thinking` blocks, the Responses API sends `reasoning` items. They are close enough to be confused and different enough to matter when reading a log to work out which upstream a turn actually went to, so the line says which one it saw rather than translating both into one house word.

    `txt` carried readable reasoning; `enc` carried only an opaque signature. Worth telling apart because the two cost the same tokens and are indistinguishable from the outside: a turn that reasoned aloud and one handed back sealed reasoning it cannot read look identical on every other field of this line.

    Kinds appear in a fixed order rather than the order they arrived, so two lines can be compared at a glance. Empty when nothing came back, which is the common case and should take no width.
    """
    if not kinds:
        return ""
    counted = [(kind, sum(1 for item in kinds if item == kind)) for kind in ("enc", "txt")]
    named = ",".join(f"{kind}:{count}" for kind, count in counted if count)
    return f"{REASONING_WORD[dialect]}({named})" if named else ""


def format_stop_reason(
    stop_reason: str, tools: tuple[str, ...], dialect: ReplyDialect = ReplyDialect.ANTHROPIC, *, color: bool = False
) -> str:
    """`tool_use(Bash,Bash,Read)` / `function_call(Bash,Bash,Read)` — the reason, and for tool calls which tools were asked for.

    Duplicates are kept and the order is the model's. The reason alone says only that the turn ended in tool calls; three `Bash` in a row and one `Bash` are very different turns, and collapsing them would hide exactly the pattern worth noticing in a log.

    A Responses upstream has no stop reason of its own, so the assembler synthesises the Anthropic one the client is owed. That synthesised word is right for the response body and wrong for this line, which reports what upstream did: there, the thing that happened was a `function_call` item. The real name is used here so a reader is not left looking for a `tool_use` in a Responses trace that never contained one.

    Colour says how much of a problem the ending was: green for a clean finish, yellow for a reply cut short at the token limit, red for one the model declined to give. A reason that ends the reply but not the work — `tool_use`, where the caller is expected to run the tools and come back — is left uncoloured, as is any reason not on the list. The names in the parentheses are quiet — see `_painted_tools`.
    """
    if not stop_reason:
        return ""
    named = [tool for tool in tools if tool]
    word = TOOL_WORD[dialect] if stop_reason == TOOL_USE_REASON else stop_reason
    reason_colour = REASON_COLOURS.get(stop_reason)
    painted = paint(word, reason_colour, color=color) if reason_colour else word
    return f"{painted}({_painted_tools(named, color=color)})" if named else painted


def _painted_tools(names: list[str], *, color: bool) -> str:
    """The tool names inside the parentheses, quiet except for the one that stops the turn.

    Dim by default because the list is context for the word in front of it: what matters at a glance is that the reply ended in tool calls, and *which* ones only once somebody is already reading. `AskUserQuestion` is the exception and gets picked out, because that tool's whole purpose is to ask a person something — the work is now blocked on somebody noticing, which is worth spotting in a scrolling log. No claim is made about the other names: a tool is any string, and plenty of others may wait on approvals or external events too. This one simply says so on its face.

    Painted in runs rather than name by name so the commas inside a run are coloured with it. Painting each name separately would leave white commas between grey names, which reads as though the separators were part of something else.
    """
    if not color:
        return ",".join(names)
    spans: list[str] = []
    run: list[str] = []
    run_colour = ""
    for name in names:
        colour = CYAN if name in ATTENTION_TOOLS else DIM
        if run and colour != run_colour:
            spans.append(paint(",".join(run), run_colour, color=True))
            run = []
        run_colour = colour
        run.append(name)
    if run:
        spans.append(paint(",".join(run), run_colour, color=True))
    return ",".join(spans)


def shown_magnitude(value: int, base: int) -> float:
    """The figure a reader will actually see, on the scale the thresholds are stated in.

    Both formatters print one decimal place, so a count just under a threshold can round *up* to the same string as one just over it — 10239 and 10240 bytes both print `10.0KB`. Deciding the colour from the raw count then puts two different colours on two identical numbers, which is precisely the confusion the colour exists to prevent. Reading the shown figure instead costs about half a percent of threshold precision and buys a line that cannot contradict itself.

    Below the scale's own switchover the formatter prints the bare count, so the ratio is left unrounded there: 999 tokens print as `999`, and rounding would call that `1.0` and colour it as though it had crossed.
    """
    return round(value / base, 1) if value >= base else value / base


def format_count(value: int) -> str:
    """Compact token counts. Bare of any byte unit, which is what tells a token column from a byte one."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def format_tokens(usage: dict[str, Any], *, unicode: bool = True, color: bool = False) -> str:
    """`↑<input>[+<cache-read>][+<cache-write>][ ↻<hit>%[+<new>%]] ↓<output>`, or empty when nothing was reported.

    The cache breakdown is additive on the input side because that is what the numbers are: reading from cache and writing to it are both ways of supplying input. The rates are shown only when there was cache activity, since `↻0%` on every uncached request is a column of noise.

    `↓output` is rendered whenever it was measured, `0` included — a request that produced no output tokens is a real and interesting outcome, and omitting it would make that indistinguishable from an endpoint that does not count output at all.

    Colouring follows upstream: the cache-read segment is dim because a cache hit is the cheap, uninteresting case, and the cache-write segment and `+new%` are cyan because they are what this request paid to store.
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

    head = f"{up}{format_count(input_tokens)}"
    if cache_read:
        head += paint(f"+{format_count(cache_read)}", DIM, color=color)
    if cache_write:
        head += paint(f"+{format_count(cache_write)}", CYAN, color=color)
    parts = [head]

    supplied = input_tokens + cache_read + cache_write
    if cache_read or cache_write:
        # Both rates, as upstream shows them: what came out of cache, and what went into it on this request. `+new%` is what tells a warm prompt apart from one that just paid to be cached, which read alone cannot.
        marker = "↻" if unicode else "cache "
        hit = round(100 * cache_read / supplied) if supplied else 0
        new = round(100 * cache_write / supplied) if supplied else 0
        rate = paint(f"{marker}{hit}%", cache_hit_colour(hit), color=color)
        if cache_write:
            rate += paint(f"+{new}%", CYAN, color=color)
        parts.append(rate)

    if "output_tokens" in usage:
        produced = read("output_tokens")
        colour = volume_colour(shown_magnitude(produced, 1000), notable=NOTABLE_K_TOKENS, heavy=HEAVY_K_TOKENS)
        parts.append(paint(f"{down}{format_count(produced)}", colour, color=color))
    return " ".join(parts)


def _subject(line: RequestLine, *, succeeded: bool, color: bool) -> list[str]:
    """Who the request was for: the model when it worked, the route when it did not.

    A mapped model is shown as `asked → answered`, because a line reporting only the resolved name hides the mapping — and a mapping doing something unintended is invisible in exactly the request where it matters. The name it resolved to is the coloured half; what was asked for is dim, since it is context for the model that actually answered.
    """
    target = paint(line.model, MAGENTA, color=color)
    named = target
    if line.requested_model and line.model and line.requested_model != line.model:
        named = f"{paint(line.requested_model, DIM, color=color)} → {target}"

    if succeeded and line.model:
        prefix = paint(f"{line.inbound_format}/", DIM, color=color) if line.inbound_format else ""
        return [f"{prefix}{named}"]
    parts = [paint(line.method, WHITE, color=color), paint(line.path, WHITE, color=color)]
    if line.model:
        parts.append(named)
    return parts


def format_arrival_line(line: RequestLine) -> str:
    """`METHOD /path [model]` — what is known when the request shows up and nothing more."""
    parts = [line.method, line.path]
    if line.model:
        parts.append(line.model)
    return " ".join(parts)


def format_completion_line(line: RequestLine, *, unicode: bool = True, color: bool = False) -> str:
    """The message body for a finished request.

    Ordered status, subject, duration, wire bytes, tokens, stop reason, retries, detail — narrowing from how it went, to what it cost, to why it ended. Every field after the subject is omitted when it has nothing to say, so a bare rejection and a full streamed answer share one column order instead of drifting into two formats.

    Colour carries meaning rather than decoration, following `copilot-api-js`: the status and the failure reason say whether to care, the model is the one name worth finding at a glance, and the duration escalates on its own so a slow request is visible without reading the number.

    What came *back* escalates too, on its own scale — bytes and output tokens both go quiet, plain, then warm as they cross an order of magnitude. What went out does not: its size follows from the request the client made and says nothing about how the reply went.
    """
    succeeded = line.status_code is not None and line.status_code < 400
    up, down = ("↑", "↓") if unicode else (">", "<")

    parts: list[str] = []
    protocols = format_protocols(line.client_protocol, line.upstream_protocol)
    if protocols:
        # Ahead of the status, so the two facts that describe the exchange itself — how it was carried and how it ended — sit together at the front.
        parts.append(paint(protocols, DIM, color=color))
    if line.status_code is not None:
        parts.append(paint(str(line.status_code), GREEN if succeeded else RED, color=color))
    parts.extend(_subject(line, succeeded=succeeded, color=color))
    if line.duration_s is not None:
        parts.append(paint(format_duration(line.duration_s), duration_colour(line.duration_s), color=color))

    # Wire bytes, one field for both directions so they read as a pair rather than as two unrelated numbers.
    # Only the returning half escalates. What this proxy sent upstream is a consequence of the request the client made and says nothing about how the reply went, so it stays quiet whatever its size.
    received_colour = (
        volume_colour(shown_magnitude(line.bytes_out, 1024), notable=NOTABLE_KB, heavy=HEAVY_KB)
        if line.bytes_out is not None
        else DIM
    )
    wire = [
        paint(f"{up}{format_bytes(line.bytes_in)}", DIM, color=color) if line.bytes_in is not None else "",
        paint(f"{down}{format_bytes(line.bytes_out)}", received_colour, color=color) if line.bytes_out is not None else "",
    ]
    parts.extend(part for part in wire if part)

    tokens = format_tokens(line.usage, unicode=unicode, color=color)
    if tokens:
        parts.append(tokens)
    if line.stop_reason:
        parts.append(format_stop_reason(line.stop_reason, line.tools, line.dialect, color=color))
    if line.attempts > 1:
        # Named on the line that reports the outcome, where the count is final. A retry still in progress is the footer's job.
        parts.append(paint(f"retries={line.attempts - 1}", YELLOW, color=color))

    rendered = " ".join(parts)
    thinking = format_thinking(line.thinking, line.dialect)
    if thinking:
        # Last, and grey. It says what the model did on its way to the answer rather than anything about the exchange, so it belongs after the fields that describe the exchange and should not compete with them.
        rendered = f"{rendered} {paint(thinking, DIM, color=color)}"
    # A colon rather than a space before the reason, matching the upstream shape and giving the eye somewhere to stop on a line that is otherwise all fields.
    return f"{rendered}: {paint(line.detail, RED, color=color)}" if line.detail else rendered


def status_for(status_code: int | None, *, failed: bool) -> str:
    """The `status` field the prefix processor turns into `[ OK ]` or `[FAIL]`.

    Driven by whether the request produced a usable response rather than by the exception type, so an upstream 500 delivered intact and a transport error that produced nothing both read as failures — which is what the person watching cares about.
    """
    if failed or status_code is None:
        return "fail"
    return "ok" if status_code < 400 else "fail"
