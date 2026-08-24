"""The vocabulary a failure is described in, and the tables that spell it in each dialect.

`.dev/docs/error-envelope/spec.md` is the authority. It is a living document — read its revision record for what changed and when, rather than pinning to a date here. Two things live here and nothing else:

- `ErrorCategory`, the closed set of *what kind of failure this is* — this proxy's own concept, not any dialect's spelling.
- `ErrorInfo`, the record one failure travels as, and the per-dialect tables that render its category.

Deliberately a leaf: importing this module loads nothing else under `app.`, and a test asserts it. That is what lets both the HTTP edge and the delivery chain describe a failure in the same terms without either importing the other. `conversion` is annotated rather than constructed for the same reason — a `default_factory=Conversion` would make this leaf import `app.pipeline.translation_driver` at runtime.

The dialect tables are keyed on the wire-format *string* rather than on `WireFormat`, which lives in `app.pipeline.request`. `WireFormat` is a `StrEnum`, so a caller holding a member indexes these directly and nothing has to convert.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.translation_driver.semantic import Conversion


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
