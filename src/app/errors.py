"""The vocabulary a failure is described in, and the tables that spell it in each dialect.

`.dev/docs/error-envelope/spec.md` is the authority. It is a living document — read its revision record for what changed and when, rather than pinning to a date here. What lives here:

- `ErrorCategory`, the closed set of *what kind of failure this is* — this proxy's own concept, not any dialect's spelling. `ErrorCondition` sits beside it for the narrower question of *which failure upstream is describing*.
- `ErrorInfo`, the record one failure travels as, and the per-dialect tables that render its category and its condition.
- The wordings a condition is **recognised** by, beside the wordings it is **spelled** in. `prompt_limit_counts` is the odd one — its return value is `app.tokenization`'s currency, not this module's — and it is here because it reads the same three patterns the predicate does; the reason is on the function.

Deliberately a leaf: importing this module loads nothing else under `app.`, and `tests/unit/test_module_boundaries.py` asserts it. That is what lets both the HTTP edge and the delivery chain describe a failure in the same terms without either importing the other. `conversion` is annotated rather than constructed for the same reason — a `default_factory=Conversion` would make this leaf import `app.pipeline.translation_driver` at runtime.

The dialect tables are keyed on the wire-format *string* rather than on `WireFormat`, which lives in `app.pipeline.request`. `WireFormat` is a `StrEnum`, so a caller holding a member indexes these directly and nothing has to convert.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.translation_driver.semantic import Conversion


class ErrorCondition(StrEnum):
    """A specific failure this proxy knows how to state in every client dialect.

    Orthogonal to `ErrorCategory`, and the split is what each answers. A category answers *what a client can do differently*; a condition answers *which supported failure happened*. The condition may come from reading an upstream body or from a deterministic proxy-side refusal. A context-window overflow and a malformed field are both `CLIENT`/400 — the category is right and is not the whole story.

    A closed set on purpose. `.dev/docs/error-envelope/spec.md` §5.5 is the authority for what may join it and for how each member is spelled per dialect; nothing goes in without a spelling in every dialect table below, which is what stops a new member from silently rendering as its category's default.
    """

    # Copilot spells this three different ways depending on which upstream leg answers (48 first-hand samples, `.dev/docs/upstream/retry-and-continuation/reports/260821-context-limit-400-examples.md`), and only one of them is a spelling a client recognises.
    CONTEXT_WINDOW_EXCEEDED = "context_window_exceeded"


class ErrorCategory(StrEnum):
    """What kind of failure, cut by *what a client can do differently about it*.

    Not cut by which exception class raised it: a class name is an implementation detail, and a rename would change the contract. Not cut by severity either — `NOT_IMPLEMENTED` and `UPSTREAM` are equally fatal to this request and send the caller to entirely different places.

    The first six members predate the spec and **keep their spelling**: `app.pipeline.hand_over` writes them into the tool call that hands a turn back, and the MCP server on the other side reads them (`.dev/docs/upstream/retry-and-continuation/decisions.md` 4.1). Renaming one would be a wire change in another repository.
    """

    CLIENT = "client"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    UPSTREAM = "upstream"
    INTERNAL = "internal"
    # Added 2026-08-23. `CLIENT` alone had to mean "your body is wrong", "no such model" and "you may not do that" at once, which is three different next steps for the caller.
    PERMISSION = "permission"
    # Separate from `PERMISSION` although both can arrive as 403, because Anthropic's own vocabulary separates them and the two send a caller to different places: settle the bill, or ask for access.
    BILLING = "billing"
    NOT_FOUND = "not_found"
    OVERLOADED = "overloaded"
    TIMEOUT = "timeout"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(slots=True)
class ErrorInfo:
    """One failure, in this proxy's own terms, before anything spells it for a client.

    Built once per failure and rendered per dialect, which is what `message-translation.md` requires of a translated path: a mapping to an internal concept, not a direct mapping between two wire shapes.

    `source_bytes` is what upstream actually sent, unparsed, and it is not for rendering — the direct path hands it to the client untouched, and a translated path that cannot read it carries it in an extension field (spec §10.1). `source_format` is empty when this proxy produced the failure itself, which is also when `source_bytes` is empty; the two answer different questions and a reader should not derive one from the other.
    """

    category: ErrorCategory
    message: str
    status_code: int
    # Which failure upstream was describing, when it was one this proxy recognises. `None` is the ordinary case and is not a defect: reading upstream's body far enough to name the condition is done for the few that change what a client does, not for every failure.
    condition: ErrorCondition | None = None
    # This proxy's own stable identifier for the failure. A dialect's declared fields rarely include it — Anthropic's `ErrorObject` declares only `type` and `message` — so treat it as a versioned extension rather than as something a client's SDK surfaces as a typed attribute.
    code: str = ""
    # Which field of the request the failure is about, when one is named. `TranslationRefused.field_path` is the source that already exists.
    param: str = ""
    # Upstream's semantic headers, already filtered. Empty for a failure this proxy produced.
    headers: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    source_format: str = ""
    source_bytes: bytes = b""
    source_content_type: str = ""
    # `None` rather than an empty `Conversion`, and the reason is structural rather than stylistic: constructing one here would make this leaf import the translation driver at runtime. `None` also reads correctly for the common case — a failure this proxy produced crossed nothing and has no losses to record.
    conversion: Conversion | None = None


# Anthropic's declared top-level error vocabulary, from `anthropic.types.shared.error_type.ErrorType`.
# Four categories collapse onto `api_error` because Anthropic draws no distinction between them. That loss is real and is **not** repaired by `ErrorInfo.code`: `code` is this project's extension with no known consumer, so what actually keeps a client's behaviour apart across those four is the HTTP status and `x-should-retry` (spec §6.2, §6.4).
# Until 2026-08-23 this table read `network_error` / `upstream_error` / `internal_error` for the last three, and those three are not in Anthropic's declared vocabulary at all — measured against the SDK's union. The claim stops there: the SDK only `cast`s the field and does not validate it, so "not declared" is not "rejected".
ANTHROPIC_ERROR_TYPES: dict[ErrorCategory, str] = {
    ErrorCategory.CLIENT: "invalid_request_error",
    ErrorCategory.AUTH: "authentication_error",
    ErrorCategory.PERMISSION: "permission_error",
    ErrorCategory.BILLING: "billing_error",
    ErrorCategory.NOT_FOUND: "not_found_error",
    ErrorCategory.RATE_LIMIT: "rate_limit_error",
    ErrorCategory.OVERLOADED: "overloaded_error",
    ErrorCategory.TIMEOUT: "timeout_error",
    ErrorCategory.NETWORK: "api_error",
    ErrorCategory.UPSTREAM: "api_error",
    ErrorCategory.INTERNAL: "api_error",
    ErrorCategory.NOT_IMPLEMENTED: "api_error",
}

# **This proxy's convention**, not OpenAI's contract. `openai.types.shared.error_object.ErrorObject.type` is a bare `str` with no `Literal` and no enum, and the published error guide gives none of these spellings a contract — measured against the installed SDK.
# Because the field is open, there is no reason to flatten `AUTH`, `PERMISSION` and `NOT_FOUND` onto `invalid_request_error`; an earlier draft did, purely to fill the column.
OPENAI_ERROR_TYPES: dict[ErrorCategory, str] = {
    ErrorCategory.CLIENT: "invalid_request_error",
    ErrorCategory.AUTH: "authentication_error",
    ErrorCategory.PERMISSION: "permission_error",
    ErrorCategory.BILLING: "insufficient_quota",
    ErrorCategory.NOT_FOUND: "not_found_error",
    ErrorCategory.RATE_LIMIT: "rate_limit_error",
    ErrorCategory.OVERLOADED: "server_error",
    ErrorCategory.TIMEOUT: "server_error",
    ErrorCategory.NETWORK: "server_error",
    ErrorCategory.UPSTREAM: "server_error",
    ErrorCategory.INTERNAL: "server_error",
    ErrorCategory.NOT_IMPLEMENTED: "server_error",
}

# Google's canonical codes, which is what a Gemini client reads out of `error.status`.
GEMINI_ERROR_STATUSES: dict[ErrorCategory, str] = {
    ErrorCategory.CLIENT: "INVALID_ARGUMENT",
    ErrorCategory.AUTH: "UNAUTHENTICATED",
    ErrorCategory.PERMISSION: "PERMISSION_DENIED",
    ErrorCategory.BILLING: "PERMISSION_DENIED",
    ErrorCategory.NOT_FOUND: "NOT_FOUND",
    ErrorCategory.RATE_LIMIT: "RESOURCE_EXHAUSTED",
    ErrorCategory.OVERLOADED: "UNAVAILABLE",
    ErrorCategory.TIMEOUT: "DEADLINE_EXCEEDED",
    ErrorCategory.NETWORK: "UNAVAILABLE",
    ErrorCategory.UPSTREAM: "INTERNAL",
    ErrorCategory.INTERNAL: "INTERNAL",
    ErrorCategory.NOT_IMPLEMENTED: "UNIMPLEMENTED",
}

ERROR_TYPES_BY_FORMAT: dict[str, dict[ErrorCategory, str]] = {
    "anthropic-messages": ANTHROPIC_ERROR_TYPES,
    "openai-chat-completions": OPENAI_ERROR_TYPES,
    "openai-responses": OPENAI_ERROR_TYPES,
    "openai-embeddings": OPENAI_ERROR_TYPES,
    "gemini-generate-content": GEMINI_ERROR_STATUSES,
}

# What this proxy tells the client, per category. Spec §6.2.
# A dialect's `type` string is not enough to define what a client does: both SDKs pick their exception class from the HTTP status, and both retry 408, 409, 429 and every `>= 500` by default — measured in `_base_client.py`.
STATUS_FOR_CATEGORY: dict[ErrorCategory, int] = {
    ErrorCategory.CLIENT: 400,
    ErrorCategory.AUTH: 401,
    ErrorCategory.PERMISSION: 403,
    ErrorCategory.BILLING: 403,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.RATE_LIMIT: 429,
    ErrorCategory.OVERLOADED: 503,
    ErrorCategory.TIMEOUT: 504,
    ErrorCategory.NETWORK: 502,
    ErrorCategory.UPSTREAM: 502,
    ErrorCategory.INTERNAL: 500,
    ErrorCategory.NOT_IMPLEMENTED: 501,
}

DEFAULT_CODE_FOR_CATEGORY: dict[ErrorCategory, str] = {
    ErrorCategory.CLIENT: "invalid_request",
    ErrorCategory.AUTH: "authentication_failed",
    ErrorCategory.PERMISSION: "permission_denied",
    ErrorCategory.BILLING: "billing_issue",
    ErrorCategory.NOT_FOUND: "not_found",
    ErrorCategory.RATE_LIMIT: "rate_limited",
    ErrorCategory.OVERLOADED: "overloaded",
    ErrorCategory.TIMEOUT: "timeout",
    ErrorCategory.NETWORK: "upstream_network_failure",
    ErrorCategory.UPSTREAM: "upstream_failure",
    ErrorCategory.INTERNAL: "proxy_internal_error",
    ErrorCategory.NOT_IMPLEMENTED: "not_implemented",
}

# The two categories where the SDKs' default would be actively wrong. Both sit at a `>= 5xx` status, so both would be retried; and both mean the same request will get the same answer however many times it is asked. `x-should-retry` is read by both SDKs — measured.
# Deliberately not set for `OVERLOADED`, `TIMEOUT` or `RATE_LIMIT`: those *are* worth retrying and the SDKs already do.
NO_RETRY_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {ErrorCategory.INTERNAL, ErrorCategory.NOT_IMPLEMENTED}
)


# What this proxy calls a recognised condition, per dialect. Spec §5.5.2.
# These *replace* the category's default `code` rather than sitting beside it: a client reading `code` is asking one question, and answering it with `invalid_request` when the answer is known to be narrower throws away the only machine-readable channel this envelope has.
# Anthropic's spelling is upstream's own on its Anthropic leg — 27 first-hand samples — rather than one invented here.
ANTHROPIC_CONDITION_CODES: dict[ErrorCondition, str] = {
    ErrorCondition.CONTEXT_WINDOW_EXCEEDED: "model_max_prompt_tokens_exceeded",
}

OPENAI_CONDITION_CODES: dict[ErrorCondition, str] = {
    ErrorCondition.CONTEXT_WINDOW_EXCEEDED: "context_length_exceeded",
}

# Gemini's error object has no `code` string — its `code` is the HTTP status and its identifier is `status`, which is the category's. So a condition adds nothing there, and the absence is the entry rather than an omission.
CONDITION_CODES_BY_FORMAT: dict[str, dict[ErrorCondition, str]] = {
    "anthropic-messages": ANTHROPIC_CONDITION_CODES,
    "openai-chat-completions": OPENAI_CONDITION_CODES,
    "openai-responses": OPENAI_CONDITION_CODES,
    "openai-embeddings": OPENAI_CONDITION_CODES,
}

# The one sentence a client is known to key on, and the reason this whole condition exists. Spec §5.5.3.
# Claude Code lowercases the serialised error object and asks whether it contains this substring — no status gate, and neither `type` nor `code` participates. Measured across 2.1.207 / 2.1.226 / 2.1.241; it is the common denominator of the three.
# Kept as a constant so the guard test and the two message forms below cannot drift apart from one another.
PROMPT_TOO_LONG_PHRASE = "prompt is too long"

# Used when upstream stated the numbers. The client's optional extraction is `/prompt is too long[^0-9]*(\d+)\s*tokens?\s*>\s*(\d+)/i`, so nothing numeric may come between the phrase and the first count.
PROMPT_TOO_LONG_WITH_COUNTS = PROMPT_TOO_LONG_PHRASE + ": {current} tokens > {limit} maximum"

# Used when it did not. Copilot's Responses leg states the condition in a sentence with no digits in it at all, and a count invented here would be shown to a user as though it had been measured. Spec §5.5.2 forbids that outright.
PROMPT_TOO_LONG_WITHOUT_COUNTS = PROMPT_TOO_LONG_PHRASE + ": the input exceeds this model's context window"


def condition_code(condition: ErrorCondition, *, wire_format: str) -> str:
    """How one dialect spells a recognised condition, or empty when it has no channel for one.

    Empty rather than a fallback spelling: a dialect with no `code` field would be handed a value it cannot carry, and the caller's own default is the right answer there.
    """
    return CONDITION_CODES_BY_FORMAT.get(wire_format, {}).get(condition, "")


# The wordings upstream uses for a context overflow, which is the other half of this module's vocabulary: what a failure is *recognised* by, beside what it is *spelled* as. Both sides live here so that the reader who changes one is looking at the other, and so `app.tokenization.limits` can learn a model's limit from the same patterns the classifier recognises the condition by, rather than keeping a second copy that drifts.
# Spec §5.5.1 is the authority, and these are the whole of it — a predicate here and a row there must be changed together.
# Evidence tiers differ and are not flattened: 48 first-hand local recordings cover the two active legs, and one third-party capture covers `/chat/completions`. The third is a real recorded response rather than a fixture, but it is not this machine's and its leg is not one this proxy drives today.
_CONTEXT_LIMIT_COUNT_PATTERNS = (
    # The `/chat/completions` wording, from the third-party capture. Zero hits in 145,781 local operations.
    re.compile(r"prompt token count of\s+(\d+)\s+exceeds the limit of\s+(\d+)", re.I),
    # The Anthropic leg's wording, and the one this proxy re-emits. 27 first-hand samples.
    re.compile(r"prompt is too long:\s*(\d+)\s+tokens\s*>\s*(\d+)\s+maximum", re.I),
)

# Matched as a fragment rather than a whole sentence, deliberately. Upstream's wording drifts: this sentence was measured as `… try again.` in August and reached a user as `… try again again.` on 2026-08-24, and its trailing `Please adjust your input and try again.` is a generic tail shared with unrelated failures.
# **Exactly one fragment, and the bare phrase `prompt is too long` is deliberately not a second one.** Upstream is observed to echo request-derived strings into `error.message` — a tool name, an id — so a fragment predicate is a predicate over text a client can partly control, and a false positive here is not cosmetic: it makes the client discard history, compact and resend, with upstream's real complaint replaced. This fragment is kept because the Responses leg offers nothing else; the bare phrase is not, because every recording that contains it also carries either the code or the counts.
_CONTEXT_LIMIT_PHRASES = ("exceeds the context window",)

# The Anthropic leg's `error.code`, and the strongest of the three signals: every other 400 on that leg carries no `code` field whatsoever.
_CONTEXT_LIMIT_CODES = frozenset({"model_max_prompt_tokens_exceeded"})


def prompt_limit_counts(message: str) -> tuple[int, int] | None:
    """The token count and the limit upstream stated, when it stated them.

    Lives here rather than in `app.tokenization` although its return value is that module's currency, because the patterns it reads are the same ones `is_context_window_exceeded` recognises the condition by. Splitting them put the same three wordings in two modules with two reasons to change; keeping the extractor beside the predicate is what makes it impossible for one to accept a sentence the other rejects — which is exactly the state this replaced.

    `None` covers two different situations that need the same handling — upstream named no numbers, and upstream named numbers that do not describe an overflow. The second is the reason for the `current > limit > 0` test: a pair that fails it is being read wrong, and acting on it would report a limit that is not one.
    """
    for pattern in _CONTEXT_LIMIT_COUNT_PATTERNS:
        match = pattern.search(message)
        if match is None:
            continue
        current, limit = (int(value) for value in match.groups())
        if current > limit > 0:
            return current, limit
    return None


def is_context_window_exceeded(*, message: str, code: str) -> bool:
    """Whether upstream's body is describing an input that does not fit the model's context window.

    Spec §5.5.1's three predicates and nothing else: upstream's own `code`, the one fragment the Responses leg leaves us, and either counted wording. The third is asked by way of `prompt_limit_counts` rather than by a fourth pattern list, so that "this sentence states an overflow" and "these are its numbers" can never disagree.

    Reads upstream's body only. Whether a failure at *this* status can be an overflow at all is a separate question with a separate answer — see `_from_upstream`, which is where a 429 that happens to contain these words is stopped.
    """
    if code in _CONTEXT_LIMIT_CODES:
        return True
    lowered = message.lower()
    if any(phrase in lowered for phrase in _CONTEXT_LIMIT_PHRASES):
        return True
    return prompt_limit_counts(message) is not None


def condition_message(condition: ErrorCondition, counts: tuple[int, int] | None) -> str:
    """The sentence a recognised condition is stated in.

    Here rather than in the classifier so that every site building an `ErrorInfo` with a condition words it the same way. The alternative — each construction site rendering its own — is how a record ends up carrying a condition and a message that disagree, and nothing in the type would say so.

    Not per dialect, and Spec §5.5.2 records that as a decision rather than an oversight: making it per dialect means rendering in the writer, which would leave `ErrorInfo.message` saying something different from what the client is sent — the same split already registered as a defect on the observability side.
    """
    if condition is ErrorCondition.CONTEXT_WINDOW_EXCEEDED:
        if counts is not None:
            current, limit = counts
            return PROMPT_TOO_LONG_WITH_COUNTS.format(current=current, limit=limit)
        return PROMPT_TOO_LONG_WITHOUT_COUNTS
    # Unreachable while the closed set has one member, and a `raise` rather than a fallback string: a condition with no sentence is a gap in this function, not something to paper over on the wire.
    raise AssertionError(f"no message defined for {condition}")


def category_for_status(status_code: int, *, upstream_type: str = "") -> ErrorCategory:
    """Which category an upstream status belongs to. Spec §5.2.

    `upstream_type` is upstream's own `error.type` where one could be read, and it exists for exactly one split: a 403 is `BILLING` rather than `PERMISSION` when upstream says so. Nothing else keys on it, because nothing else needs a second opinion once the status is known.
    """
    if status_code == 403:
        return ErrorCategory.BILLING if upstream_type == "billing_error" else ErrorCategory.PERMISSION
    if status_code == 401:
        return ErrorCategory.AUTH
    if status_code == 404:
        return ErrorCategory.NOT_FOUND
    if status_code in (408, 504):
        return ErrorCategory.TIMEOUT
    if status_code == 429:
        return ErrorCategory.RATE_LIMIT
    if status_code in (503, 529):
        return ErrorCategory.OVERLOADED
    if 400 <= status_code < 500:
        return ErrorCategory.CLIENT
    if status_code >= 500:
        return ErrorCategory.UPSTREAM
    # Reached only by a status below 400, which is not a failure at all. `INTERNAL` rather than a guess: something upstream of here decided a success was an error, and that is this side's problem.
    return ErrorCategory.INTERNAL


class ApiError(Exception):
    """The legacy carrier, kept because `app.models.common` and `app.streaming.sse` still reference it.

    Neither of those is reachable from a live route — `.dev/docs/error-envelope/deferred.md` §E-5 registers the question of archiving them. `wire_type` therefore reads the Anthropic table, which is what it read before that table gained the other dialects; whether it should be per-dialect is moot until it has a caller.
    """

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory | None = None,
        status_code: int = 500,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.category = category or category_for_status(status_code)
        self.code = code
        self.request_id = request_id

    @property
    def wire_type(self) -> str:
        return ANTHROPIC_ERROR_TYPES[self.category]


def classify_error(error: BaseException) -> ErrorCategory:
    """The legacy classifier. `app.pipeline.error_classify.describe` is the one the live chain uses.

    Kept alongside `ApiError` for the same reason and with the same open question.
    """
    if isinstance(error, ApiError):
        return error.category
    if isinstance(error, ConnectionError | TimeoutError):
        return ErrorCategory.NETWORK
    return ErrorCategory.INTERNAL
