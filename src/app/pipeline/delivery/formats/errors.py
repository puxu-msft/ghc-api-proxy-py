"""How each dialect spells an error body.

One module rather than one per format, because "what an error looks like in dialect X" is a single question and the answers are read against each other. The streaming carriers stay with their own format modules — `.dev/docs/error-envelope/spec.md` §6.3 established they are *not* the same shape as the JSON body for every dialect, so putting them together would suggest a symmetry OpenAI Responses does not have. Anthropic's two carriers *are* the same object, and `anthropic_messages.error_frame` builds it from here rather than repeating it.

Nothing decides anything here. Which category, which status, which code — all of that is settled before an `ErrorInfo` arrives; this only spells it.
"""

from typing import Any

import orjson

from app.errors import (
    ANTHROPIC_ERROR_TYPES,
    ERROR_TYPES_BY_FORMAT,
    GEMINI_ERROR_STATUSES,
    OPENAI_ERROR_TYPES,
    ErrorInfo,
)
from app.pipeline.translation_driver.semantic import LossCode

# The field upstream's own error travels in when this proxy could not interpret it. Ruled by the user 2026-08-23 (spec §10.1) after three candidates: keep the original structured under a named key, rather than passing it through in a dialect the client cannot parse or flattening it into a sentence the client has to parse twice.
#
# It is this project's extension. No dialect declares it, so a client's SDK will not surface it as a typed attribute — the Python SDKs keep the whole body on the exception, which is where it can be read from.
UPSTREAM_ERROR_KEY = "upstream_error"


def _upstream_remains(info: ErrorInfo) -> Any:
    """Upstream's own error, structured if it parses and verbatim if it does not.

    Only present when the reader said it could not interpret what upstream sent — an error this proxy *did* understand is already expressed by the envelope around it, and repeating the original would say the same thing twice in two vocabularies.

    `latin-1` is the fallback rather than `utf-8` with replacement, and the difference matters for exactly the case this exists to serve: every byte maps, so nothing is lost. A replacement character would be this proxy editing the one thing it was asked to pass on untouched.
    """
    if info.conversion is None or not info.conversion.has(LossCode.UPSTREAM_ERROR_NOT_INTERPRETED):
        return None
    if not info.source_bytes:
        return None
    try:
        return orjson.loads(info.source_bytes)
    except orjson.JSONDecodeError:
        try:
            return info.source_bytes.decode(info.source_content_type.partition("charset=")[2] or "utf-8")
        except (UnicodeDecodeError, LookupError):
            return info.source_bytes.decode("latin-1")


def _anthropic(info: ErrorInfo) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "type": ANTHROPIC_ERROR_TYPES[info.category],
        "message": info.message,
    }
    if info.code:
        detail["code"] = info.code
    if info.param:
        detail["param"] = info.param
    remains = _upstream_remains(info)
    if remains is not None:
        detail[UPSTREAM_ERROR_KEY] = remains
    # The outer `type` is Anthropic's, not a repetition: its error body is a tagged union at the top level and an SDK reads that tag before the nested one.
    return {"type": "error", "error": detail}


def _openai(info: ErrorInfo) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "message": info.message,
        "type": OPENAI_ERROR_TYPES[info.category],
        # Declared by the SDK as `Optional[str]`, so `None` is the shape for "not applicable" rather than an omission — a client reading `.param` gets a value either way.
        "param": info.param or None,
        "code": info.code or None,
    }
    remains = _upstream_remains(info)
    if remains is not None:
        detail[UPSTREAM_ERROR_KEY] = remains
    return {"error": detail}


def _gemini(info: ErrorInfo) -> dict[str, Any]:
    detail: dict[str, Any] = {
        # Google puts the HTTP status here, not a string identifier; `status` below is the canonical name.
        "code": info.status_code,
        "message": info.message,
        "status": GEMINI_ERROR_STATUSES[info.category],
    }
    remains = _upstream_remains(info)
    if remains is not None:
        detail[UPSTREAM_ERROR_KEY] = remains
    return {"error": detail}


_WRITERS = {
    "anthropic-messages": _anthropic,
    "openai-chat-completions": _openai,
    "openai-responses": _openai,
    "openai-embeddings": _openai,
    "gemini-generate-content": _gemini,
}


def write_error(info: ErrorInfo, *, wire_format: str) -> dict[str, Any]:
    """Spell one failure in the dialect the client is speaking.

    An unknown format falls back to Anthropic's shape rather than raising. The alternative is a `KeyError` on the one path whose job is to report failures, which would replace a client's answer with a traceback — and this proxy's primary product path is Anthropic, so the fallback is the one most clients can read.

    That fallback is unreachable today: `_WRITERS` covers every `WireFormat` member, and a test asserts it does. It exists for the version of this file where someone adds a member and not a writer.
    """
    return _WRITERS.get(wire_format, _anthropic)(info)


def formats_with_writers() -> frozenset[str]:
    """Which dialects can be spelled. Read by the test that pins this against `WireFormat`."""
    return frozenset(_WRITERS) & frozenset(ERROR_TYPES_BY_FORMAT)
