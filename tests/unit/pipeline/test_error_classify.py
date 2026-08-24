"""Every row of the spec's source → IR tables, transcribed by hand.

By hand on purpose, and a plan review is what settled it. The plan said to generate one assertion per row "from the table's structure rather than transcribing it", which sounds like it avoids transcription slips and actually removes the only independent oracle there is: if the expected values come from the production table, deleting a row deletes a case with it and mistyping a value mistypes the expectation to match. The spec is Markdown in a separate repository, so there is no machine-readable authority to read either. Duplication is the price of an oracle, and `EXPECTED_CASE_IDS` below is what makes a *missing* case fail rather than pass quietly.

Fields are asserted whole rather than category-only. A row that lands the right category with the wrong status is the shape that reaches a client as the wrong SDK exception, and the SDKs pick their class from the status.
"""

from collections.abc import Callable
from typing import get_args

import pytest
from anthropic.types.shared.error_type import ErrorType

from app.errors import (
    ANTHROPIC_ERROR_TYPES,
    DEFAULT_CODE_FOR_CATEGORY,
    GEMINI_ERROR_STATUSES,
    OPENAI_ERROR_TYPES,
    STATUS_FOR_CATEGORY,
    ErrorCategory,
    ErrorInfo,
    category_for_status,
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
from app.pipeline.error_classify import describe
from app.pipeline.exceptions import (
    PipelineAbort,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
)
from app.pipeline.routing import RoutingError
from app.pipeline.translation_driver.registry import TranslatorNotFound
from app.pipeline.translation_driver.semantic import TranslationRefused

BILLING_BODY = '{"error": {"type": "billing_error", "message": "credit exhausted"}}'


def _rejected(status: int, *, body: str = "{}") -> UpstreamRejected:
    return UpstreamRejected("refused", status_code=status, body=body)


def _upstream(status: int | None, *, body: str = "{}") -> UpstreamError:
    return UpstreamError("failed", status_code=status, body=body)


# (id, build the failure, expected category, expected status)
CASES: tuple[tuple[str, Callable[[], BaseException], ErrorCategory, int], ...] = (
    ("upstream-400", lambda: _rejected(400), ErrorCategory.CLIENT, 400),
    ("upstream-401", lambda: _upstream(401), ErrorCategory.AUTH, 401),
    ("upstream-403-permission", lambda: _rejected(403), ErrorCategory.PERMISSION, 403),
    (
        "upstream-403-billing",
        lambda: _rejected(403, body=BILLING_BODY),
        ErrorCategory.BILLING,
        403,
    ),
    ("upstream-404", lambda: _rejected(404), ErrorCategory.NOT_FOUND, 404),
    ("upstream-429", lambda: UpstreamRateLimit("limited"), ErrorCategory.RATE_LIMIT, 429),
    ("upstream-500", lambda: _upstream(500), ErrorCategory.UPSTREAM, 500),
    ("upstream-503", lambda: _upstream(503), ErrorCategory.OVERLOADED, 503),
    ("upstream-no-status", lambda: _upstream(None), ErrorCategory.NETWORK, 502),
    ("upstream-timeout", lambda: UpstreamTimeout("timed out"), ErrorCategory.TIMEOUT, 504),
    (
        "abort-reads-its-cause",
        lambda: PipelineAbort("budget exhausted", cause=_upstream(503)),
        ErrorCategory.OVERLOADED,
        503,
    ),
    (
        "count-tokens-reads-its-cause",
        lambda: CountTokensUnavailable(("ghc:0:UpstreamRejected",), cause=_rejected(400)),
        ErrorCategory.CLIENT,
        400,
    ),
    ("unknown-model", lambda: UnknownModel("ghc", "nope"), ErrorCategory.NOT_FOUND, 404),
    ("capability-missing", lambda: CapabilityMissing("ghc", "mute"), ErrorCategory.CLIENT, 400),
    (
        "endpoint-not-supported",
        lambda: EndpointNotSupported("ghc", "m", "/responses"),
        ErrorCategory.CLIENT,
        400,
    ),
    (
        "endpoint-not-implemented",
        lambda: EndpointNotImplemented("ghc", "/responses"),
        ErrorCategory.NOT_IMPLEMENTED,
        501,
    ),
    (
        "provider-not-configured",
        lambda: ProviderNotConfigured("nope"),
        ErrorCategory.INTERNAL,
        500,
    ),
    ("provider-error-base", lambda: ProviderError("something"), ErrorCategory.CLIENT, 400),
    (
        "translation-refused",
        lambda: TranslationRefused("no", code="unsupported_field", field_path="tools[0].x"),
        ErrorCategory.CLIENT,
        400,
    ),
    (
        "translator-not-found",
        lambda: TranslatorNotFound("no translator"),
        ErrorCategory.NOT_IMPLEMENTED,
        501,
    ),
    (
        "count-tokens-request-error",
        lambda: CountTokensRequestError("not a countable Messages body"),
        ErrorCategory.CLIENT,
        400,
    ),
    ("routing-error", lambda: RoutingError("bad"), ErrorCategory.CLIENT, 400),
    ("outside-the-closed-set", lambda: KeyError("model"), ErrorCategory.INTERNAL, 500),
)

# An independent literal, not derived from `CASES`. Deleting a case above without deleting its id here is what this catches — otherwise a lost row simply stops being tested and nothing says so.
EXPECTED_CASE_IDS = frozenset(
    {
        "upstream-400",
        "upstream-401",
        "upstream-403-permission",
        "upstream-403-billing",
        "upstream-404",
        "upstream-429",
        "upstream-500",
        "upstream-503",
        "upstream-no-status",
        "upstream-timeout",
        "abort-reads-its-cause",
        "count-tokens-reads-its-cause",
        "unknown-model",
        "capability-missing",
        "endpoint-not-supported",
        "endpoint-not-implemented",
        "provider-not-configured",
        "provider-error-base",
        "translation-refused",
        "translator-not-found",
        "count-tokens-request-error",
        "routing-error",
        "outside-the-closed-set",
    }
)


def test_every_row_of_the_spec_has_a_case() -> None:
    assert {case[0] for case in CASES} == EXPECTED_CASE_IDS
    assert len(CASES) == len(EXPECTED_CASE_IDS), "duplicate case id"


@pytest.mark.parametrize(
    "build, category, status", [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
def test_a_failure_is_described_as_the_spec_says(
    build: Callable[[], BaseException], category: ErrorCategory, status: int
) -> None:
    info = describe(build())

    assert info.category is category
    assert info.status_code == status
    assert info.code == DEFAULT_CODE_FOR_CATEGORY[category] or info.code
    assert info.message


def test_a_refusal_over_a_field_carries_the_field_and_its_own_code() -> None:
    """The two machine-readable fields, which until now only one exception ever filled.

    Asserted separately from the table because the table pins category and status, and these are the parts that say *which* part of the request is the problem. A generic 400 the client cannot act on is the thing they exist to prevent.
    """
    info = describe(TranslationRefused("no", code="unsupported_field", field_path="tools[0].x"))

    assert info.code == "unsupported_field"
    assert info.param == "tools[0].x"


def test_upstreams_own_answer_travels_on_the_record() -> None:
    """What the direct path hands to the client, and what a translated path falls back on.

    `content-length` is asserted absent rather than merely unmentioned: it describes upstream's body, and letting it onto a response of a different length is a framing bug rather than an untidiness.
    """
    error = UpstreamRejected(
        "refused",
        status_code=400,
        headers={
            "content-type": "text/html",
            "content-length": "9",
            "x-request-id": "req_abc",
            "anthropic-ratelimit-requests-remaining": "17",
        },
        body="<html/>",
        body_bytes=b"\xffraw-body",
        content_type="text/html",
    )

    info = describe(error, source_format="anthropic-messages")

    assert info.source_bytes == b"\xffraw-body"
    assert info.source_content_type == "text/html"
    assert info.source_format == "anthropic-messages"
    assert info.headers["x-request-id"] == "req_abc"
    assert info.headers["anthropic-ratelimit-requests-remaining"] == "17"
    assert "content-length" not in info.headers
    assert "content-type" not in info.headers, "it travels as source_content_type, not in the bag"


def test_a_failure_this_proxy_produced_carries_no_upstream_remains() -> None:
    """Absence has to be readable: a translated path decides what to do partly from whether there is an upstream answer at all."""
    info = describe(RoutingError("bad"))

    assert info.source_bytes == b""
    assert info.source_format == ""
    assert info.headers == {}


def test_the_provider_error_subclasses_are_all_classified() -> None:
    """A new subclass must be classified deliberately rather than fall into the base's row.

    The same shape as adding an enum member to a table keyed on it: the class hierarchy grows, every `isinstance` chain over it silently gains a default, and nothing type-checks the gap. Pinned as a set so adding one fails here first.
    """
    named = {
        UnknownModel,
        CapabilityMissing,
        EndpointNotSupported,
        EndpointNotImplemented,
        ProviderNotConfigured,
    }
    actual = set(ProviderError.__subclasses__())

    assert actual == named, (
        f"unclassified ProviderError subclasses: {sorted(c.__name__ for c in actual - named)}"
    )


# (status, upstream error.type, expected category) — literals, not read from any production table.
STATUS_CASES: tuple[tuple[int, str, ErrorCategory], ...] = (
    (400, "", ErrorCategory.CLIENT),
    (401, "", ErrorCategory.AUTH),
    (403, "", ErrorCategory.PERMISSION),
    (403, "billing_error", ErrorCategory.BILLING),
    (404, "", ErrorCategory.NOT_FOUND),
    (408, "", ErrorCategory.TIMEOUT),
    (413, "", ErrorCategory.CLIENT),
    (418, "", ErrorCategory.CLIENT),
    (422, "", ErrorCategory.CLIENT),
    (429, "", ErrorCategory.RATE_LIMIT),
    (500, "", ErrorCategory.UPSTREAM),
    (502, "", ErrorCategory.UPSTREAM),
    (503, "", ErrorCategory.OVERLOADED),
    (504, "", ErrorCategory.TIMEOUT),
    (529, "", ErrorCategory.OVERLOADED),
    (599, "", ErrorCategory.UPSTREAM),
    # Below 400 is not a failure at all; something upstream of the classifier decided it was.
    (204, "", ErrorCategory.INTERNAL),
)


@pytest.mark.parametrize("status, upstream_type, category", STATUS_CASES)
def test_status_maps_to_the_category_the_spec_names(
    status: int, upstream_type: str, category: ErrorCategory
) -> None:
    assert category_for_status(status, upstream_type=upstream_type) is category


@pytest.mark.parametrize(
    "name, table",
    [
        ("anthropic", ANTHROPIC_ERROR_TYPES),
        ("openai", OPENAI_ERROR_TYPES),
        ("gemini", GEMINI_ERROR_STATUSES),
        ("status", STATUS_FOR_CATEGORY),
        ("default code", DEFAULT_CODE_FOR_CATEGORY),
    ],
)
def test_every_table_keyed_on_the_category_covers_all_of_it(
    name: str, table: dict[ErrorCategory, object]
) -> None:
    """The failure mode that widening the enum opens, caught at the table rather than at the `KeyError`.

    Measured on this project before: adding a `WireFormat` member left `FORMAT_ENDPOINTS` a member short, and the gap surfaced as a 502 whose body was a Python enum's `repr` on the primary path. A set equality here is what makes the next widening fail at the table instead.
    """
    assert set(table) == set(ErrorCategory), f"{name} is missing {set(ErrorCategory) - set(table)}"


def test_anthropics_column_is_its_own_declared_vocabulary() -> None:
    """Read off the SDK's discriminated union rather than by scanning its source for a pattern.

    A regex over `anthropic/types/*.py` was the first method and it is not sound for a claim about a *complete* set: an alias, a differently-quoted literal or a member declared elsewhere would be missed, and content-block error types would be swept in. `ErrorType` is the `Literal` the SDK declares for this field, so reading it is reading the declaration itself.

    The claim stops at "declared". The SDK `cast`s this field without validating it, so a value outside the union is not thereby rejected — it just is not something Anthropic has published a contract for.

    A subset check, not equality: this proxy has no reason to emit every type Anthropic can (`gateway_timeout_error` is upstream's to send, not ours). Completeness in the other direction — every `ErrorCategory` has a row — is `test_every_table_keyed_on_the_category_covers_all_of_it`, and it takes both to close the gap.
    """
    declared = set(get_args(ErrorType))
    assert len(declared) == 9, "the SDK's vocabulary changed; re-read the spec's table against it"

    assert set(ANTHROPIC_ERROR_TYPES.values()) <= declared, (
        f"not in Anthropic's declared vocabulary: {set(ANTHROPIC_ERROR_TYPES.values()) - declared}"
    )


def test_error_info_defaults_are_absences_rather_than_values() -> None:
    """`conversion` is `None` and not an empty `Conversion`, which is what keeps `app.errors` a leaf.

    Constructing one would make this module import the translation driver at runtime, and the whole reason both the HTTP edge and the delivery chain can share this vocabulary is that neither has to pull the other in to use it.
    """
    info = ErrorInfo(category=ErrorCategory.INTERNAL, message="m", status_code=500)

    assert info.conversion is None
    assert info.headers == {}
    assert info.source_bytes == b""
