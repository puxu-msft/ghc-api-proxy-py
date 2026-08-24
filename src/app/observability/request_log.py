"""The per-request console lines.

The frame is `[PREFIX] HH:MM:SS METHOD /path ...`, with the fixed-width prefix and the timestamp supplied by the structlog processor chain. What this module builds is the part after them. That frame was taken from `.dev/docs/archived-2604-rewrite/DESIGN.md`, which the user ruled obsolete on 2026-08-20 — it is what this project shipped and has kept, not a standing decision, and no current document restates it.

The field order follows `copilot-api-js`, whose real rendered lines look like `[ OK ] 14:25:36 200 anthropic/claude-opus-4-8 1.2s ↑1.0k+8.0k+1.0k ↻80% ↓456 end_turn`. Two things there are deliberate rather than incidental, and both are kept: a **successful** line collapses method and path into `<inbound-format>/<model>`, because once a request has worked, which model answered is the thing worth reading and the route is noise; a line that did **not** succeed keeps `METHOD /path`, because that is what has to be reproduced. Which of the two a line is comes from the verdict passed to `format_completion_line`, never from the status code: a streamed reply's code is settled when upstream's headers arrive, so a stream that tore an hour later still carries a 200 and would otherwise be dressed as an answer that arrived.

Bytes and tokens both use `↑`/`↓` and are told apart by unit, again as upstream does: bytes carry `B`/`KB`/`MB`, token counts are bare with a `k`/`m` suffix. Every field is dropped when it has nothing to say, so the line grows only with what actually happened.

Kept pure and separate from the emitting call so a line can be asserted without a logger, a terminal or a served request.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from app.observability.footer import format_bytes, format_duration
from app.observability.terminal import (
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    RED,
    YELLOW,
    cache_hit_colour,
    duration_colour,
    paint,
    volume_colour,
)
from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.hand_over import one_line

# What to call the same two things under each upstream, abbreviated to fit a line. Held here, in the layer that renders, because which word to print is a display decision; what happened is the record's business and it says only which upstream described it.
# `tool_use` is the Anthropic stop reason the Responses assembler synthesises for the client's benefit. Recognised by name so the line can put back what upstream actually sent.
TOOL_USE_REASON = "tool_use"
REASONING_WORD = {ReplyDialect.ANTHROPIC: "think", ReplyDialect.RESPONSES: "reason"}
TOOL_WORD = {ReplyDialect.ANTHROPIC: TOOL_USE_REASON, ReplyDialect.RESPONSES: "function_call"}

# Where a reply stops being ordinary. Bytes are 1024-based, matching what `format_bytes` prints. A count inside the printed figure's rounding band can show the same number in a different colour from one just over the threshold; the thresholds are the round numbers rather than the rounding band, and that is the accepted trade.
#
# Bytes are per dialect; tokens are not. The two dialects are counted at the same place and in the same units — `_counted_upstream` wraps `aiter_bytes()`, so both figures are post-decompression bytes off the same wire — and on this proxy's traffic a Responses reply still costs tens of times more per output token than an Anthropic one. That is what the Responses wire costs rather than anything this proxy does, and two measured causes account for it. Item-level events carry a 416-byte opaque item id: in the capture at `exp/260820-websearch-probe/raw/C2-responses-search-stream-response.txt`, 13 item-level events each carry one, and across its three `output_text.delta` frames those ids are 63.7% of the bytes against 3.6% for the text delivered. Responses splits a reply into fine-grained deltas, so that fixed per-event cost is paid many times over. Separately, `response.created`, `response.in_progress` and `response.completed` each echo the entire `tools` array, which is why replies of 7-8 output tokens from the current client are observed at 57-58KB — a floor that follows from that client's tool declarations and their schema sizes, not a constant of the protocol: the C2 capture declares one tool and runs to 16KB in total.
#
# So one pair of numbers cannot discriminate on both paths. Measured over 4,546 production requests (snapshot 2026-08-21): the old 10KB/100KB left 98.8% of Responses lines painted notable and 49.6% heavy — a column lit on almost every line has stopped carrying information — while producing 11.8%/0.1% on Anthropic traffic, which is the intended shape. The Responses pair is therefore chosen to restore that same qualitative shape rather than by scaling the old numbers by the byte ratio: roughly the top decile notable and well under one percent heavy (9.8%/0.9% on that snapshot). What the colour means is "unusual for this path", so the display goes by path-relative frequency instead. These shares move with traffic and are a sighting rather than a contract — the thresholds are round numbers that produced the right shape, not a fitted constant. Tokens need no such split: a token means the same thing whoever emitted it.
RECEIVED_BYTES_THRESHOLDS = {
    ReplyDialect.ANTHROPIC: (10 * 1024, 100 * 1024),
    ReplyDialect.RESPONSES: (384 * 1024, 4 * 1024 * 1024),
}
NOTABLE_TOKENS, HEAVY_TOKENS = 1_000, 10_000

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

# What a count adds to the format prefix on a successful line. Written as a suffix on the format rather than as a format of its own, because that is what it is: the same inbound body, asked a different question.
COUNT_TOKENS_SUFFIX = "-count-tokens"

# The endings a request line can report, spelled as `STATUS_PREFIXES` keys because that is the one place they are turned into something a reader sees.
#
# `gone` is not a failure and not a success: nobody was left to receive the answer. `retry` is both at once, and that is the whole reason it exists: the client got a complete, well-formed reply and will act on it, while the upstream attempt behind it did not finish. Reporting it as `ok` would hide every interrupted turn; reporting it as `fail` would say the client got nothing.
type LogStatus = Literal["ok", "fail", "gone", "retry"]

# How the status code and the detail are painted, on the same three tiers the prefix uses rather than on the code's own value. A streamed reply's code is settled when upstream's headers arrive, so a torn stream carries a green-looking 200 that says nothing about how the next several minutes went; the verdict is what the colour has to follow.
# `gone` is amber rather than red on the ruling `STATUS_PREFIXES` records for `[GONE]`: on a proxy fronting an interactive client, cancelling a turn is routine, and painting every Esc the same red as an upstream reset would bury the resets. Amber keeps it out of the green that means "nothing to look at" without claiming the proxy broke.
# The same three tiers as `logging.PREFIX_COLOURS`, which paints the prefix on the far left of the same line. Restated rather than imported because the two answer different questions — that one colours a fixed word, this one a number and a sentence — but they are one judgement about how much of a problem each verdict is, and a change to either belongs in both.
STATUS_COLOURS: dict[LogStatus, str] = {"ok": GREEN, "fail": RED, "gone": YELLOW, "retry": YELLOW}


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

    `model` empty means routing never resolved one — a rejected body, an unknown model. It is then left out rather than printed as a placeholder, because a placeholder reads as a model actually named that.

    `bytes_in` / `bytes_out` are wire bytes in each direction; `usage` is the upstream's own token accounting, keyed as Anthropic reports it. The two are separate facts and a request can have either without the other — a rejected body has bytes and no tokens, a cached hit has tokens and almost no bytes.

    `count_provider` is set only on a token-counting request, and names the counting provider that produced the number; `count_provider_reason` carries what was tried before it, when anything was. See `format_count_provider`. `count_tokens` is the endpoint the request arrived at, which is the same fact one step earlier: it is true of a count that failed before any provider ran, where `count_provider` is empty.

    `losses` is what translation could not carry, in the order it was recorded. It exists here rather than beside the translator because this record is the one place a per-request fact is written down once, so anything that later wants it — the JSONL file today, a query over it tomorrow — reads the same tuple. **The rendered console line does not show it**: `extensions-not-carried` fires on most translated requests, and a field that appears on nearly every line has stopped telling anyone anything. Whether it is worth a column should be decided from the counter's frequency, not from this record's existence.
    """

    method: str
    path: str
    request_id: str = ""
    message_id: str = ""
    inbound_format: str = ""
    # Whether this was a count rather than a turn. Not a wire format of its own — the body is an Anthropic Messages body either way — so it is kept beside `inbound_format` rather than folded into it, and the two are joined only when the line is rendered.
    count_tokens: bool = False
    client_protocol: str = ""
    upstream_protocol: str = ""
    requested_model: str = ""
    model: str = ""
    status_code: int | None = None
    started_at: str = ""
    duration_s: float | None = None
    first_upstream_byte_s: float | None = None
    # How the upstream stream was paced, for the question the duration cannot answer: a request that took four minutes because upstream went quiet for most of one of them, and a request that took four minutes producing bytes throughout, are the same number here and different incidents. `upstream_max_gap_s` is the longest silence between two arrivals from upstream, measured only *between* them — the wait before the first is `first_upstream_byte_s` above, and the wait after the last is not a gap between anything. `None` means fewer than two arrivals, which is not the same as no silence.
    # A gap is timed against what `with_idle_timeout` counts as activity, so the number can be read straight against `upstream_request_timeouts.stream_idle`: a max gap sitting just under the configured idle timeout is a request that nearly died, and nothing else on this record says so. The default for that setting is 0 — no terminator at all — which is exactly the configuration where this field is the only account of a silence anyone will ever get.
    # **Not rendered on the console line**, following `first_upstream_byte_s` above, which is the same sort of fact and has never been on it. A line that already carries between eight and twelve fields pays for each new one on every request, and the case worth catching is rare and already visible there: a stalled turn shows up as a duration the colour scale escalates on its own. The gap is the *next* question — was it slow or was it silent — and the answer belongs where a reader who has decided to ask it goes, which is the record.
    upstream_max_gap_s: float | None = None
    upstream_chunks: int = 0
    bytes_in: int | None = None
    bytes_out: int | None = None
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    terminal_seen: bool = False
    stop_reason: str = ""
    blocks: int = 0
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    count_provider: str = ""
    count_provider_reason: str = ""
    # Whose words to use for the reasoning and tool-call fields. See `ReplyDialect`; it travels with the reply summary the line is built from.
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    attempts: int = 1
    # What each replayed attempt was replacing, in order. A transparent replay is invisible to the client by design; it used to be invisible here too, leaving `retries=N` as a count with no cause.
    replaced_failures: tuple[str, ...] = ()
    # What upstream did *after* saying everything it had to say. Not an ending and not a failure, so it neither sets the status nor competes with `detail` — both of those describe how the turn came out, and this describes the connection it came out over.
    tore_after_terminal: str = ""
    detail: str = ""
    upstream_conn: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    # What translation could not carry, one entry per recorded loss, in the order recorded. Each entry is `{"direction": "request"|"response", "code": …, "detail": …}`. Direction is a property of the loss rather than a second field, because "what did this request lose" is one question and answering it from two lists is how the two drift apart.
    # `code` is the machine-readable half and `detail` the human one, which is the division `LossCode` was written for; both are kept because the code alone cannot say *which* extensions were dropped, and the detail alone cannot be counted.
    losses: tuple[dict[str, str], ...] = ()


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


def format_pending_tools(tools: tuple[str, ...], *, color: bool = False) -> str:
    """`called(Bash,Read)` — what the turn asked for, on a line that never learned how it ended.

    A separate word from `format_stop_reason`'s, and deliberately neither upstream's. `tool_use` and `function_call` both say the reply *ended* in tool calls; this is the line where nothing said the reply ended at all, and borrowing either word would put an ending on a turn that was cut off. What is true is only that these blocks completed and these tools were named, which is worth reading — a truncated turn that had already asked for three tools is a different incident from one that produced nothing.

    `called` rather than `tools`, which was the first spelling and collided with the other meaning the word carries here: the tool *declarations* a request sends. A reader glancing at a log line has no way to tell "this request declared Bash and Read" from "this turn called them", and those are opposite ends of the exchange.
    """
    named = [tool for tool in tools if tool]
    return f"called({_painted_tools(named, color=color)})" if named else ""


def format_count_provider(provider: str, reason: str = "", *, color: bool = False) -> str:
    """`provider(ghc)` / `provider(ghc-failed,local)` — which counting provider produced the number on this line, and what was tried before it.

    Named for the thing `inbound.anthropic_count_tokens.providers` configures, because that is what it reports: `ghc` is upstream's own measurement and `local` is this proxy's calibrated estimate, and they are the two values of `CountTokensProvider`. The word `count` was the first spelling and became redundant once the format prefix started carrying `-count-tokens`, where it belongs — that says what kind of request this was, which is not what this field is for.

    The parenthetical is the trail, in the order it happened: what was tried and did not answer, then the provider that did. `provider(ghc-failed,local)` is an upstream that was asked and could not answer; `provider(no-counter,local)` is a route with no upstream counter, which estimates every time and is working as configured; a bare `provider(local)` is an operator who configured the estimate rather than asking. Those three were one word until 2026-08-20, and two of them are incidents — this line's own defect one level up, where the failure was never absent, it was wearing the ordinary case's clothes.

    Not coloured, ruled with the spelling. A count that always estimates is the steady state on a translated route, so painting the field would fire on the ordinary case daily and stop meaning anything; the degraded reading is carried by the words instead, which also survives a log file.

    The trail is dim and the word is not, being context for what the field is — the same division `format_pending_tools` makes with its tool names.
    """
    if not provider:
        return ""
    trail = f"{reason},{provider}" if reason else provider
    return f"provider({paint(trail, DIM, color=color)})"


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
        colour = volume_colour(produced, notable=NOTABLE_TOKENS, heavy=HEAVY_TOKENS)
        parts.append(paint(f"{down}{format_count(produced)}", colour, color=color))
    return " ".join(parts)


def _subject(line: RequestLine, *, succeeded: bool, color: bool) -> list[str]:
    """Who the request was for: the model when the request worked, the route when it did not.

    `succeeded` is the line's verdict rather than its status code, so a stream that tore mid-turn takes the route form even though it answered 200 — that line is one somebody has to reproduce, and dressing it as `<inbound-format>/<model>` said the opposite of its own `[FAIL]` prefix. A client that left takes the route form too: nobody received the answer, so nothing about it earned the shape that means one arrived.

    A mapped model is shown as `asked → answered`, because a line reporting only the resolved name hides the mapping — and a mapping doing something unintended is invisible in exactly the request where it matters. The name it resolved to is the coloured half; what was asked for is dim, since it is context for the model that actually answered.

    On a successful line the route collapses into the format prefix, and a count then loses the one thing that said which endpoint it hit: `/v1/messages` and `/v1/messages/count_tokens` take the same body and so report the same format. The suffix puts that back. Composed here rather than carried on the record, for the same reason the reasoning and tool words are — what to call it is a display decision, and what happened is that a count-tokens endpoint was asked.
    """
    target = paint(line.model, MAGENTA, color=color)
    named = target
    if line.requested_model and line.model and line.requested_model != line.model:
        named = f"{paint(line.requested_model, DIM, color=color)} → {target}"

    if succeeded and line.model:
        label = f"{line.inbound_format}{COUNT_TOKENS_SUFFIX}" if line.count_tokens else line.inbound_format
        prefix = paint(f"{label}/", DIM, color=color) if label else ""
        return [f"{prefix}{named}"]
    # Left at the terminal's own foreground. An explicit white here was brighter than the untouched text beside it and read as emphasis, which the route does not deserve: on a failed line it is reference material, and the status and the reason are what carry the weight.
    parts = [line.method, line.path]
    if line.model:
        parts.append(named)
    return parts


def format_arrival_line(line: RequestLine) -> str:
    """`METHOD /path [model]` — what is known when the request shows up and nothing more."""
    parts = [line.method, line.path]
    if line.model:
        parts.append(line.model)
    return " ".join(parts)


def format_completion_line(line: RequestLine, *, status: LogStatus, unicode: bool = True, color: bool = False) -> str:
    """The message body for a finished request.

    Ordered status, subject, duration, wire bytes, tokens, ending, retries, detail, request id — narrowing from how it went, to what it cost, to why it ended. The ending is the stop reason, or on a token-counting request the counting provider that answered it. Every field after the subject is omitted when it has nothing to say, so a bare rejection and a full streamed answer share one column order instead of drifting into two formats.

    The request id is the exception to that order and sits past the end of it, because it is not a fact about the request: it is the join key to the structured record, a UUID as wide as several real fields put together, and on a line that worked there is nothing to go and join to. So it is printed only when the line reports something other than success, and printed last, where a reader who wants it knows to look and a reader scanning the fields never has to step over it. The record file carries it on every request either way, which is what makes dropping it here cost nothing.

    `status` is the whole line's verdict and is **required**, because the status code cannot supply it: a streamed reply's code is fixed when upstream's headers arrive, so a stream that tore halfway is a failure wearing a 200. It decides three things together — the prefix the processor will print, whether this line takes the successful shape, and how the code is painted — so that a line can no longer say `[FAIL]` while every other part of it reads as an answer that arrived. No default, deliberately: the one wrong value here is `ok`, and a default would hand it to exactly the caller who forgot to think about it.

    Colour carries meaning rather than decoration, following `copilot-api-js`: the status and the failure reason say whether to care, the model is the one name worth finding at a glance, and the duration escalates on its own so a slow request is visible without reading the number.

    What came *back* escalates too, on its own scale — bytes and output tokens both go quiet, plain, then warm as they cross an order of magnitude. What went out does not: its size follows from the request the client made and says nothing about how the reply went.
    """
    succeeded = status == "ok"
    up, down = ("↑", "↓") if unicode else (">", "<")

    parts: list[str] = []
    protocols = format_protocols(line.client_protocol, line.upstream_protocol)
    if protocols:
        # Ahead of the status, so the two facts that describe the exchange itself — how it was carried and how it ended — sit together at the front.
        parts.append(paint(protocols, DIM, color=color))
    if line.status_code is not None:
        parts.append(paint(str(line.status_code), STATUS_COLOURS[status], color=color))
    parts.extend(_subject(line, succeeded=succeeded, color=color))
    if line.duration_s is not None:
        parts.append(paint(format_duration(line.duration_s), duration_colour(line.duration_s), color=color))

    # Wire bytes, one field for both directions so they read as a pair rather than as two unrelated numbers.
    # Only the returning half escalates. What this proxy sent upstream is a consequence of the request the client made and says nothing about how the reply went, so it stays quiet whatever its size.
    # The thresholds come from the dialect for the reason recorded at `RECEIVED_BYTES_THRESHOLDS`: subscripted rather than looked up with a default, exactly as `REASONING_WORD` and `TOOL_WORD` are, so a dialect added later fails here instead of silently being judged by another path's sense of large.
    notable_bytes, heavy_bytes = RECEIVED_BYTES_THRESHOLDS[line.dialect]
    received_colour = (
        volume_colour(line.bytes_out, notable=notable_bytes, heavy=heavy_bytes) if line.bytes_out is not None else DIM
    )
    wire = [
        paint(f"{up}{format_bytes(line.bytes_in)}", DIM, color=color) if line.bytes_in is not None else "",
        paint(f"{down}{format_bytes(line.bytes_out)}", received_colour, color=color) if line.bytes_out is not None else "",
    ]
    parts.extend(part for part in wire if part)

    tokens = format_tokens(line.usage, unicode=unicode, color=color)
    if tokens:
        parts.append(tokens)
    if line.count_provider:
        # A count has no reply and therefore no stop reason, so this is its ending. The order is for the reader rather than for the state machine: `count_provider` is set only on the count branch, which returns before a reply is ever aggregated, so no reachable request carries both and swapping these two arms would change nothing that runs.
        parts.append(format_count_provider(line.count_provider, line.count_provider_reason, color=color))
    elif line.stop_reason:
        parts.append(format_stop_reason(line.stop_reason, line.tools, line.dialect, color=color))
    elif line.tools:
        # No reason came back, but the tools did. Dropping them with the reason lost the only thing that said what the turn had got through before it stopped.
        parts.append(format_pending_tools(line.tools, color=color))
    if line.attempts > 1:
        # Named on the line that reports the outcome, where the count is final. A retry still in progress is the footer's job.
        retries = f"retries={line.attempts - 1}"
        if line.replaced_failures:
            # The count says a replay happened; these say what each one replaced. All of them, because a review put a different failure in the second of three attempts and the first one did not describe it. Bounded as a whole, not per entry: each is already cut to the same limit the hand-over message uses, and three of them side by side would still outrun a line.
            retries = f"{retries} after {one_line('; '.join(line.replaced_failures))}"
        parts.append(paint(retries, YELLOW, color=color))
    if line.tore_after_terminal:
        # Its own segment, added whatever the ending was. Written first as a case inside `detail`, which put it in an `elif` against the ending — and a `max_tokens` hand-over is both at once, so the hand-over's detail silently took the slot and the tear was reported nowhere at all.
        parts.append(paint(f"upstream closed abruptly after finishing the turn: {line.tore_after_terminal}", YELLOW, color=color))

    rendered = " ".join(parts)
    thinking = format_thinking(line.thinking, line.dialect)
    if thinking:
        # Last, and grey. It says what the model did on its way to the answer rather than anything about the exchange, so it belongs after the fields that describe the exchange and should not compete with them.
        rendered = f"{rendered} {paint(thinking, DIM, color=color)}"
    # A colon rather than a space before the reason, matching the upstream shape and giving the eye somewhere to stop on a line that is otherwise all fields.
    if line.detail:
        # The same tier as the status code, because this is that verdict's explanation and cannot be louder than it. Fixed red here left a cancelled turn reading as an incident — amber prefix, amber 200, red account of why — which is the reading `STATUS_COLOURS` exists to prevent.
        rendered = f"{rendered}: {paint(line.detail, STATUS_COLOURS[status], color=color)}"
    if line.request_id and status != "ok":
        # Full rather than shortened: this is the join key between the console line and its structured record, so two simultaneous failures must never become ambiguous. Past the detail as well as past the fields — the detail is what the reader came for, and a UUID wedged in front of it would be read as part of the explanation.
        rendered = f"{rendered} {paint(f'req={line.request_id}', DIM, color=color)}"
    return rendered


def status_for(status_code: int | None, *, override: LogStatus | None = None) -> LogStatus:
    """The `status` field the prefix processor turns into `[ OK ]`, `[FAIL]` or `[GONE]`.

    Driven by whether the request produced a usable response rather than by the exception type, so an upstream 500 delivered intact and a transport error that produced nothing both read as failures — which is what the person watching cares about.

    `override` carries what the status code cannot. A streaming response's status is fixed the moment upstream's headers arrive and stays 200 however the next several minutes go, so the code that watched the delivery end is the only thing that knows whether an answer actually arrived — and, separately, whether anyone was still there to receive it. One value rather than a flag per outcome, because these are alternatives and a pile of booleans would let two of them be true at once.
    """
    if override is not None:
        return override
    if status_code is None:
        return "fail"
    return "ok" if status_code < 400 else "fail"
