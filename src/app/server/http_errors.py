"""How a failure from the pipeline is spelled as HTTP.

Split out of `app.server.handler` on 2026-08-22. This is the edge's half of that module: it maps the pipeline's closed exception set onto a status, a few headers and a body. Named `http_errors` rather than `errors` because `app.errors` already exists and means something else.
"""

from typing import Any

from app.model_provider import ProviderError
from app.pipeline.count_tokens import CountTokensUnavailable
from app.pipeline.driver import CountTokensRequestError
from app.pipeline.exceptions import (
    PipelineAbort,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
)
from app.pipeline.routing import RoutingError
from app.pipeline.translation_driver.registry import TranslatorNotFound
from app.pipeline.translation_driver.semantic import (
    TranslationRefused,
)


def error_status(error: BaseException) -> int:
    """Map a failure to the status the client should see.

    A routing or capability refusal means the request is unserviceable, not that upstream failed.
    It must not be reported as a bad gateway.

    Nor must an upstream answer be flattened into one. A client that gets 429 can back off and a client that gets 400 can fix its body; both learn nothing from a 502, which says the proxy itself broke. Everything used to land on that 502 because the SDK's exceptions were outside the closed set — see `app.model_provider.ghc_client.errors`.

    An abort that ended a retry sequence is read through to the failure that ended it, for the same reason: running out of retries does not change what upstream said, and the client can still act on it. Without this every retryable failure that spent its budget arrived as that same 502.
    """
    if isinstance(error, PipelineAbort) and error.cause is not None:
        return error_status(error.cause)
    if isinstance(
        error,
        ProviderError
        | RoutingError
        | TranslatorNotFound
        | CountTokensRequestError
        | TranslationRefused,
    ):
        return 400
    if isinstance(error, CountTokensUnavailable):
        # Every configured counter failed. Reachable when `providers` names only `ghc`;
        # with `local` in the list the estimate has no way to fail on the normal path.
        return 503
    if isinstance(error, UpstreamRateLimit):
        return 429
    if isinstance(error, UpstreamTimeout):
        return 504
    if isinstance(error, UpstreamRejected):
        # Upstream's own verdict on the request. Passed through so the client is told what is wrong with what it sent, rather than that some gateway failed.
        return error.status_code
    return 502

def error_headers(error: BaseException) -> dict[str, str]:
    """The few upstream headers a client needs in order to act on a failure.

    `Retry-After` only: it is the one that changes what a well-behaved client does next. An allowlist rather than forwarding upstream's set, which carries its own framing headers.

    Read through an abort to the failure that ended the retries, so a rate limit that exhausted its budget still tells the client how long to wait.
    """
    if isinstance(error, PipelineAbort) and error.cause is not None:
        return error_headers(error.cause)
    if isinstance(error, UpstreamRateLimit) and error.retry_after is not None:
        return {"retry-after": str(int(error.retry_after))}
    return {}

def error_body(error: BaseException) -> dict[str, Any]:
    body: dict[str, Any] = {"type": type(error).__name__, "message": str(error)}
    # The abort's own message already names both the budget that ran out and the failure that ran it out, so it stays as the message. What is read off the cause instead are the structured fields — upstream's code, the field it named, its own body — which say what the prose cannot be parsed for.
    detail: BaseException = (
        error.cause if isinstance(error, PipelineAbort) and error.cause is not None else error
    )
    code = getattr(detail, "code", "")
    if isinstance(code, str) and code:
        # A stable identifier for what went wrong, where the class name is only a category and the message is prose. A client that wants to react to one particular refusal — rather than matching on English that may be reworded — has this to key on.
        body["code"] = code
    field_path = getattr(detail, "field_path", "")
    if isinstance(field_path, str) and field_path:
        # Which part of the request caused it. A refusal that names the field is one the client can act on; one that does not leaves it to guess which of its tools was the problem.
        body["field_path"] = field_path
    upstream = getattr(detail, "body", "")
    if isinstance(upstream, str) and upstream:
        # What upstream actually said. Named as upstream's rather than merged, so nothing reads our wrapper's wording as though the model had produced it.
        body["upstream"] = upstream
    return {"error": body}
