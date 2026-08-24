"""One failure, one HTTP response.

Split out of `app.server.handler` on 2026-08-22 and rewritten on 2026-08-23, when `.dev/docs/error-envelope/spec.md` first became the criterion this is built against. That Spec is a living document and is amended whenever a ruling or a measurement changes what it should say; read its revision record rather than treating any date as the version this was written for. It was three functions — a status, some headers, a body dict — and every caller handed the third to `JSONResponse`. That arrangement **cannot** express what the spec requires of a direct path: `JSONResponse` takes an object to serialize and picks its own content type, so upstream's own bytes have nowhere to go. So it is one factory that returns a `Response`, and it decides between two entirely different answers.

The two answers, from the user's ruling of 2026-08-23:

- **Direct path, failure from upstream** — the client and upstream speak the same dialect, so this proxy has no business having an opinion. Upstream's bytes, status and semantic headers go out untouched, including the fields nobody here recognises.
- **Everything else** — the failure becomes an `ErrorInfo` and a writer spells it in the client's dialect.

Classification of what the *pipeline* raises lives in `app.pipeline.error_classify`. What is classified here is the handful of sources only the edge ever holds: a body that will not parse, a body that is not an object, a route registered but not implemented, and `InboundRequestError` — which is defined one module over and would cost a `pipeline -> server` edge to classify from the other side.
"""

from collections.abc import Mapping

from fastapi.responses import JSONResponse, Response

from app.errors import (
    DEFAULT_CODE_FOR_CATEGORY,
    NO_RETRY_CATEGORIES,
    STATUS_FOR_CATEGORY,
    ErrorCategory,
    ErrorInfo,
)
from app.pipeline.delivery.formats.errors import write_error
from app.pipeline.error_classify import describe

# Headers that describe *this* response rather than upstream's. `content-length` is the dangerous one — it is upstream's byte count and Starlette computes its own — and the rest frame a connection this response is not on.
# Narrower than the floor `error_classify` already applied, and applied again here because a caller may hand in an `ErrorInfo` this edge built rather than one that came through there.
_NEVER_FORWARDED = frozenset(
    {
        "content-length",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "te",
        "trailer",
        "upgrade",
    }
)


def proxy_error(
    category: ErrorCategory, message: str, *, code: str = "", param: str = ""
) -> ErrorInfo:
    """An `ErrorInfo` for a failure the edge holds without an exception to classify.

    Three of the spec's rows arrive this way — an unparseable body, a body that is not an object, a route whose `implemented` is false — because each is a `return` rather than a `raise`. Building the record here is what lets them share one envelope with everything else instead of each inventing its own.
    """
    return ErrorInfo(
        category=category,
        message=message,
        status_code=STATUS_FOR_CATEGORY[category],
        code=code or DEFAULT_CODE_FOR_CATEGORY[category],
        param=param,
    )


def _outbound_headers(info: ErrorInfo, *, direct: bool) -> dict[str, str]:
    """What goes on the wire beside the body.

    On a direct path these are upstream's own, minus this response's framing — the rate-limit counters, the request id, `Retry-After` in whatever form upstream wrote it. Until this landed the only header a client ever saw was a `Retry-After` reformatted from a parsed float, and only on a 429; everything else, including `x-request-id`, was dropped.

    `x-should-retry` is synthesised **only** for the two categories where an SDK's default would be actively wrong. Both SDKs read the header and both retry every `>= 500` by default, so a 501 meaning "nobody built this" would otherwise be asked for again and again.

    The `not direct` term is **structural rather than reachable**, and saying so is the point: no upstream status maps to `INTERNAL` or `NOT_IMPLEMENTED` — `category_for_status` sends every `>= 500` to `UPSTREAM` — so a direct answer can never satisfy the second condition today. A mutation removing this term left every test green, which is how that was established rather than assumed. It stays because it states the rule that would otherwise have to be rediscovered: on a direct path upstream's headers are the answer, and appending to them would be this proxy having an opinion about a conversation it is only carrying.
    """
    headers = {
        name: value for name, value in info.headers.items() if name.lower() not in _NEVER_FORWARDED
    }
    if not direct and info.category in NO_RETRY_CATEGORIES:
        headers["x-should-retry"] = "false"
    return headers


def error_response(
    source: BaseException | ErrorInfo,
    *,
    inbound_format: str,
    translated: bool = True,
) -> Response:
    """The response one failure becomes.

    `translated` defaults to `True` — the answer that renders — because that is the one that is safe when a caller does not know. Passing upstream's bytes on requires knowing the client speaks upstream's dialect; rendering does not require knowing anything.

    A direct-path answer is only possible when there are bytes to pass on. A failure that happened before upstream answered has none, and falls through to the writer even on a direct path — which is the spec's §3.3, not an exception to §3.1.
    """
    info = source if isinstance(source, ErrorInfo) else describe(source, source_format=inbound_format)
    direct = not translated and bool(info.source_bytes)
    if direct:
        return Response(
            content=info.source_bytes,
            status_code=info.status_code,
            headers=_outbound_headers(info, direct=True),
            # Upstream's own declaration. `None` when it made none, which leaves Starlette's default rather than this proxy asserting what upstream's bytes are.
            # Set here rather than as a `content-type` header: a first draft did both, and a mutation showed the header line was dead — `media_type` wins, so the extra assignment looked like the mechanism and was not.
            media_type=info.source_content_type or None,
        )
    return JSONResponse(
        write_error(info, wire_format=inbound_format),
        status_code=info.status_code,
        headers=_outbound_headers(info, direct=False),
    )


def error_status(error: BaseException) -> int:
    """Kept for callers that only want the number. `error_response` is what serves a client."""
    return describe(error).status_code


def error_headers(error: BaseException) -> Mapping[str, str]:
    """Kept for the same reason as `error_status`."""
    return _outbound_headers(describe(error), direct=False)
