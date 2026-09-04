"""Which `ErrorInfo` a failure from the pipeline is.

`.dev/docs/error-envelope/spec.md` §5 is the authority; every row of its tables has a branch here and a hand-transcribed case in `tests/unit/pipeline/test_error_classify.py`.

**This module deliberately does not cover every source the spec lists.** Three of them have no exception at all — a body that will not parse, a body that is not an object, a route registered but not implemented — and a fourth, `InboundRequestError`, is defined in `app.server.inbound`. Importing that from here would put a `pipeline -> server` edge into a graph that has none, to classify a failure the edge already holds in its hand. So the edge builds those `ErrorInfo` values itself and this module classifies what the pipeline raises. Two classifiers, each where its inputs are; one record, one set of writers.

What is *not* split is the vocabulary: both sides produce the same `ErrorInfo` and the same writers render it, which is what makes "streaming and non-streaming say the same thing" a property of the structure rather than of two places agreeing.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from app.anthropic.header_policy import RESPONSE_FLOOR
from app.errors import (
    DEFAULT_CODE_FOR_CATEGORY,
    STATUS_FOR_CATEGORY,
    ErrorCategory,
    ErrorInfo,
    UpstreamCondition,
    category_for_status,
    condition_message,
    is_context_window_exceeded,
    prompt_limit_counts,
)
from app.model_provider.codebuddy_client.auth_state import (
    AuthRefreshFailed,
    AuthStateInvalid,
    AuthStateMissing,
)
from app.model_provider.registry import ProviderNotConfigured
from app.model_provider.types import (
    CapabilityMissing,
    EndpointNotImplemented,
    EndpointNotSupported,
    ProviderError,
    UnknownModel,
)
from app.pipeline.count_tokens import CountTokensRequestError, CountTokensUnavailable
from app.pipeline.exceptions import (
    PipelineAbort,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
)
from app.pipeline.routing import RoutingError
from app.pipeline.translation_driver.registry import TranslatorNotFound
from app.pipeline.translation_driver.semantic import Conversion, LossCode, TranslationRefused

# The `ProviderError` subclasses the spec names, most specific first. A `dict` keyed on the class would answer only for an exact type; this is walked in order so a future subclass of, say, `UnknownModel` still lands on its parent's row rather than on the base's.
_PROVIDER_ROWS: tuple[tuple[type[ProviderError], ErrorCategory], ...] = (
    (UnknownModel, ErrorCategory.NOT_FOUND),
    (CapabilityMissing, ErrorCategory.CLIENT),
    (EndpointNotSupported, ErrorCategory.CLIENT),
    # Its own docstring: "The model advertises the endpoint but this proxy does not drive it." That is this proxy's gap, and calling it a bad request would blame the client for a capability nobody built.
    (EndpointNotImplemented, ErrorCategory.NOT_IMPLEMENTED),
    # An operator naming a provider that is not configured. Nothing the client sends can change it.
    (ProviderNotConfigured, ErrorCategory.INTERNAL),
    # The CodeBuddy desktop login state: missing, unreadable, or refused by the
    # refresh endpoint. The client cannot fix any of these by resending — the fix
    # is logging into the desktop app or pointing the config at a live state file.
    (AuthStateMissing, ErrorCategory.AUTH),
    (AuthStateInvalid, ErrorCategory.AUTH),
    (AuthRefreshFailed, ErrorCategory.AUTH),
)


def _forwardable(headers: dict[str, str]) -> dict[str, str]:
    """Upstream's headers minus the ones that describe *this* response's framing.

    Only the unconditional floor is applied here. The operator-configurable blacklist needs the config, which lives at the edge, so the edge narrows this further — this end just never lets a `content-length` describing upstream's body escape onto a response of a different length.

    `content-type` is in the floor and is therefore dropped here too. That is not the same as losing it: it travels on `ErrorInfo.source_content_type`, and the direct path sets it explicitly rather than letting it ride in a bag that also carries framing.
    """
    return {name: value for name, value in headers.items() if name.lower() not in RESPONSE_FLOOR}


def _from_upstream(error: UpstreamError | UpstreamRejected, *, source_format: str) -> ErrorInfo:
    """An upstream failure that came back with a response.

    The category comes from the status, not from which of our exception classes wrapped it: `UpstreamRejected` and `UpstreamError` differ by whether *retrying* could help, which is a different question from what the client should be told.

    `status_code` is upstream's own where it has one. A transport failure has none, and `NETWORK`'s own status stands in — that is the one case where this side invents the number, because there was no answer to pass on.
    """
    status = error.status_code
    if status is None:
        # Nothing came back, so there is nothing to have failed to interpret.
        return ErrorInfo(
            category=ErrorCategory.NETWORK,
            message="upstream could not be reached",
            status_code=STATUS_FOR_CATEGORY[ErrorCategory.NETWORK],
            code=DEFAULT_CODE_FOR_CATEGORY[ErrorCategory.NETWORK],
            headers=_forwardable(dict(error.headers)),
            source_format=source_format,
            source_bytes=error.body_bytes,
            source_content_type=error.content_type,
        )
    read = _read_upstream_error(error.body)
    category = category_for_status(status, upstream_type=read.kind)
    # The body says what it says; whether a failure at *this* status can be an overflow at all is the other half, and it is answered here because only here is the status known.
    # `CLIENT` rather than "any 4xx": a 401 or a 429 whose text happens to contain these words is not an overflow, and the difference is not academic — the primary client acts on the phrase with no status gate of its own, so a rate limit restated this way would make it discard history and resend immediately, which is the worst available response to being rate limited. Spec §5.5.1.
    condition = read.condition if category is ErrorCategory.CLIENT else None
    conversion = Conversion()
    if not read.interpreted:
        conversion.record(
            LossCode.UPSTREAM_ERROR_NOT_INTERPRETED,
            f"{error.content_type or 'no content-type'} at {status}",
        )
    return ErrorInfo(
        category=category,
        condition=condition,
        # Built here rather than taken from `str(error)`, which is the SDK's `__str__` and changes shape with upstream's content type: a Python `dict` repr for JSON, the raw text with no prefix for HTML, and just `Error code: 400` for an empty body. Nothing in this project knew what it was putting on the wire.
        # A recognised condition is restated rather than quoted — spec §5.5.2, and the reason it is not cosmetic is §5.5.3.
        message=(
            _condition_message(read)
            if condition is not None
            else f"upstream returned {status}: {read.message}"
            if read.message
            else f"upstream returned {status}"
        ),
        status_code=status,
        # The category's default. A recognised condition narrows it, but only per dialect, so that substitution belongs to the writer rather than here.
        code=DEFAULT_CODE_FOR_CATEGORY[category],
        headers=_forwardable(dict(error.headers)),
        source_format=source_format,
        source_bytes=error.body_bytes,
        source_content_type=error.content_type,
        conversion=conversion,
    )


@dataclass(frozen=True, slots=True)
class _UpstreamRead:
    """What could be got out of upstream's error body, and whether anything could.

    `interpreted` is the field that matters downstream: it is what decides whether the client is handed upstream's original alongside this proxy's envelope (spec §10.1). It is deliberately not derived from `message` being non-empty — an error object with an empty message is still an error object we read.

    `condition` is a second, narrower reading and answers a different question. `interpreted` asks whether the body had a shape we know; `condition` asks whether the failure it describes is one we can restate. A body can be fully interpreted and name no condition, which is the ordinary case.
    """

    interpreted: bool
    message: str = ""
    kind: str = ""
    condition: UpstreamCondition | None = None
    counts: tuple[int, int] | None = None


def _read_upstream_error(body: str) -> _UpstreamRead:
    """Upstream's error body, read as far as the three dialects agree.

    All three nest under `error`: Anthropic gives `{type, message}`, OpenAI `{message, type, param, code}`, Gemini `{code, message, status}`. So `error.message` and `error.type` are the two fields worth asking for, and a body that has neither shape is one this proxy did not interpret. `error.code` joins them for the one condition whose strongest signal is carried there.

    Shallow on purpose. The point is not to mirror upstream's error model — it is to decide three things: whether a 403 is billing, whether the original has to travel because we could not read it, and whether upstream is describing a failure this proxy can restate in the client's own idiom.
    """
    if not body:
        # No body at all is not the same as a body we could not read: there is nothing to hand on either way, so it is not worth telling the client we failed to interpret nothing.
        return _UpstreamRead(interpreted=True)
    try:
        parsed: object = json.loads(body)
    except ValueError:
        return _UpstreamRead(interpreted=False)
    if not isinstance(parsed, Mapping):
        return _UpstreamRead(interpreted=False)
    nested: object = cast(Mapping[str, Any], parsed).get("error")
    if not isinstance(nested, Mapping):
        return _UpstreamRead(interpreted=False)
    detail = cast(Mapping[str, Any], nested)
    message: object = detail.get("message")
    kind: object = detail.get("type")
    upstream_code: object = detail.get("code")
    text = message if isinstance(message, str) else ""
    code = upstream_code if isinstance(upstream_code, str) else ""
    condition = (
        UpstreamCondition.CONTEXT_WINDOW_EXCEEDED
        if is_context_window_exceeded(message=text, code=code)
        else None
    )
    return _UpstreamRead(
        interpreted=True,
        message=text,
        kind=kind if isinstance(kind, str) else "",
        condition=condition,
        # Only upstream's own numbers. Nothing here estimates: a count invented on this side is shown to a user as a measurement, and the client does read it out of this sentence.
        counts=prompt_limit_counts(text) if condition is not None else None,
    )


def _condition_message(read: _UpstreamRead) -> str:
    """The sentence for a condition this proxy recognised, in the idiom a client acts on.

    No `upstream returned <status>:` prefix, unlike the general case. That prefix marks a quotation, and this is not one — the condition was recognised, so the proxy is speaking. The status it repeats is already on the response.
    """
    assert read.condition is not None
    return condition_message(read.condition, read.counts)


def _proxy_error(category: ErrorCategory, message: str, *, code: str = "", param: str = "") -> ErrorInfo:
    """A failure this proxy produced. No upstream answer exists, so nothing is carried from one."""
    return ErrorInfo(
        category=category,
        message=message,
        status_code=STATUS_FOR_CATEGORY[category],
        code=code or DEFAULT_CODE_FOR_CATEGORY[category],
        param=param,
    )


def describe(error: BaseException, *, source_format: str = "") -> ErrorInfo:
    """Turn a failure the pipeline raised into the record every writer renders from.

    `source_format` names the dialect upstream answered in, so a translated path can tell what it is reading. Empty for a failure that never reached upstream.
    """
    # First, because an abort that ended a retry sequence is not itself the thing the client can act on. Running out of retries does not change what upstream said.
    if isinstance(error, PipelineAbort) and error.cause is not None:
        return describe(error.cause, source_format=source_format)
    # Also first: every configured counter failed, and *why* is the part that matters. Flattening this to one status made an upstream 400 and an upstream 500 arrive identically — measured, both came back 503 with none of upstream's body.
    if isinstance(error, CountTokensUnavailable) and error.cause is not None:
        return describe(error.cause, source_format=source_format)

    if isinstance(error, UpstreamRateLimit):
        return _from_upstream(error, source_format=source_format)
    if isinstance(error, UpstreamTimeout):
        return _proxy_error(ErrorCategory.TIMEOUT, str(error))
    if isinstance(error, UpstreamRejected | UpstreamError):
        return _from_upstream(error, source_format=source_format)

    if isinstance(error, ProviderError):
        for kind, category in _PROVIDER_ROWS:
            if isinstance(error, kind):
                return _proxy_error(category, str(error))
        # An unnamed subclass, or the base itself. `CLIENT` keeps today's behaviour rather than guessing a new one — changing what a client does about a failure nobody has produced yet is worse than leaving it. `test_error_classify` pins the subclass set so a new one has to be classified deliberately.
        return _proxy_error(ErrorCategory.CLIENT, str(error))

    if isinstance(error, TranslationRefused):
        return _proxy_error(
            ErrorCategory.CLIENT, str(error), code=error.code, param=error.field_path
        )
    if isinstance(error, TranslatorNotFound):
        # Not `CLIENT`. There is nothing wrong with the client's body; this proxy has not built the crossing it asked for.
        return _proxy_error(ErrorCategory.NOT_IMPLEMENTED, str(error))
    if isinstance(error, CountTokensRequestError):
        # A body that cannot be read as a countable request. The client's, not this proxy's — and it was landing on `INTERNAL`/500 until a test caught the omission, which is what an unlisted branch costs.
        return _proxy_error(ErrorCategory.CLIENT, str(error))
    if isinstance(error, RoutingError):
        return _proxy_error(ErrorCategory.CLIENT, str(error))

    # Anything outside the closed set. `INTERNAL` rather than `UPSTREAM`, and the difference is who a reader goes to look at: this is a failure nothing here anticipated, which makes it ours.
    return _proxy_error(ErrorCategory.INTERNAL, str(error))
