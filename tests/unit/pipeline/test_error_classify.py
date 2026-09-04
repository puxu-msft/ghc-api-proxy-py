"""Every row of the spec's source → IR tables, transcribed by hand.

By hand on purpose, and a plan review is what settled it. The plan said to generate one assertion per row "from the table's structure rather than transcribing it", which sounds like it avoids transcription slips and actually removes the only independent oracle there is: if the expected values come from the production table, deleting a row deletes a case with it and mistyping a value mistypes the expectation to match. The spec is Markdown in a separate repository, so there is no machine-readable authority to read either. Duplication is the price of an oracle, and `EXPECTED_CASE_IDS` below is what makes a *missing* case fail rather than pass quietly.

Fields are asserted whole rather than category-only. A row that lands the right category with the wrong status is the shape that reaches a client as the wrong SDK exception, and the SDKs pick their class from the status.
"""

from collections.abc import Callable
from typing import cast, get_args

import pytest
from anthropic.types.shared.error_type import ErrorType

from app.errors import (
    ANTHROPIC_CONDITION_CODES,
    ANTHROPIC_ERROR_TYPES,
    CONDITION_CODES_BY_FORMAT,
    DEFAULT_CODE_FOR_CATEGORY,
    GEMINI_ERROR_STATUSES,
    OPENAI_CONDITION_CODES,
    OPENAI_ERROR_TYPES,
    STATUS_FOR_CATEGORY,
    ErrorCategory,
    ErrorCondition,
    ErrorInfo,
    category_for_status,
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
from app.pipeline.delivery.formats.errors import formats_with_writers, write_error
from app.pipeline.error_classify import describe
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    PromptTokenLimitExceeded,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamRejected,
    UpstreamTimeout,
    classify,
)
from app.pipeline.request import WireFormat
from app.pipeline.retry import reason_for
from app.pipeline.routing import RoutingError
from app.pipeline.translation_driver.registry import TranslatorNotFound
from app.pipeline.translation_driver.semantic import TranslationRefused
from app.tokenization.admission import TokenAdmissionObservation, TokenAdmissionOutcome

BILLING_BODY = '{"error": {"type": "billing_error", "message": "credit exhausted"}}'


def _rejected(status: int, *, body: str = "{}") -> UpstreamRejected:
    return UpstreamRejected("refused", status_code=status, body=body)


def _upstream(status: int | None, *, body: str = "{}") -> UpstreamError:
    return UpstreamError("failed", status_code=status, body=body)


def _prompt_limit_exceeded() -> PromptTokenLimitExceeded:
    return PromptTokenLimitExceeded(
        TokenAdmissionObservation(
            attempt=0,
            origin="proxy",
            outcome=TokenAdmissionOutcome.REJECTED,
            target_format="openai-responses",
            model="gpt-model",
            provider="ghc",
            catalog_generation=7,
            catalog_refreshed_at="2026-09-04T00:00:00+00:00",
            tokenizer="o200k_base",
            max_prompt_tokens=922_000,
            max_context_window_tokens=1_050_000,
            field_path="input[2].content[0].text",
            field_kind="input_text",
            field_utf8_byte_count=2_265_280,
            field_token_count=1_375_742,
        )
    )


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
    ("proxy-prompt-limit", _prompt_limit_exceeded, ErrorCategory.CLIENT, 400),
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
        "proxy-prompt-limit",
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
        AuthRefreshFailed,
        AuthStateInvalid,
        AuthStateMissing,
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


# Upstream's own bytes, verbatim from `.dev/docs/upstream/retry-and-continuation/reports/260821-context-limit-400-examples.md`. Transcribed rather than constructed for the same reason as `CASES` above: a body assembled from what this side expects to find in it cannot disagree with this side.
# The trailing newline on the Responses-leg bodies is on the wire — `content-length: 147` matches only with it.
RESPONSES_LEG_OVERFLOW = '{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again.","code":"invalid_request_body"}}\n'
# The same failure as reported to a user on 2026-08-24, with upstream's wording drifted by one word. It is the reason the predicate matches a fragment and not the sentence.
RESPONSES_LEG_OVERFLOW_DRIFTED = '{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again again.","code":"invalid_request_body"}}\n'
ANTHROPIC_LEG_OVERFLOW = '{"error":{"code":"model_max_prompt_tokens_exceeded","message":"prompt is too long: 1051542 tokens > 1000000 maximum","type":"invalid_request_error"},"request_id":"req_011CdqwDkJy9YDgyzVF2fixv","type":"error"}'
# The control that matters most: same leg, same `error.code`, an entirely unrelated failure. On this leg `invalid_request_body` is shared by a malformed field, a bad id prefix and the overflow, so a classifier keying on it would restate all three as an overflow.
RESPONSES_LEG_UNRELATED = '{"error":{"message":"Invalid \'max_output_tokens\': integer below minimum value. Expected a value >= 16, but got 8 instead.","code":"invalid_request_body"}}\n'

# One body per spec predicate, each carrying **only** that predicate's signal. The recorded samples above cannot do this job: the Anthropic-leg one carries the code, the counts and the phrase at once, so deleting any one predicate leaves the other two to catch it and the deletion goes unnoticed. Measured — a reviewer removed the code lookup entirely and 302 tests stayed green.
# Constructed, and labelled as such. They are not claims about what upstream sends; they are the only way to ask about one predicate at a time.
ONLY_THE_CODE = '{"error":{"code":"model_max_prompt_tokens_exceeded","message":"the model could not accept this request"}}'
ONLY_THE_FRAGMENT = '{"error":{"message":"Your input exceeds the context window of this model.","code":"invalid_request_body"}}'
ONLY_THE_ANTHROPIC_COUNTS = '{"error":{"message":"prompt is too long: 210000 tokens > 200000 maximum"}}'
ONLY_THE_CHAT_COMPLETIONS_COUNTS = '{"error":{"message":"prompt token count of 13613 exceeds the limit of 12288"}}'
# The wording that was accepted for one afternoon and is now rejected: the bare phrase, no counts, no code. Upstream is observed to echo request-derived strings into `error.message`, so a bare fragment is a predicate over text a client can partly influence — and a false positive makes the client throw away history and resend.
BARE_PHRASE_ONLY = '{"error":{"message":"prompt is too long"}}'


def _overflow_rejection(body: str, *, status: int = 400) -> UpstreamRejected:
    """Upstream's 400 as this proxy receives it, with the bytes and the content type it really carried.

    Deliberately not `_rejected` above: that one takes a status and defaults its body, and these cases turn on the body.
    """
    return UpstreamRejected(
        "upstream rejected the request",
        status_code=status,
        body=body,
        body_bytes=body.encode(),
        content_type="text/plain; charset=utf-8",
    )


@pytest.mark.parametrize(
    "case, body",
    [
        ("responses leg", RESPONSES_LEG_OVERFLOW),
        ("responses leg, wording drifted", RESPONSES_LEG_OVERFLOW_DRIFTED),
        ("anthropic leg", ANTHROPIC_LEG_OVERFLOW),
    ],
)
def test_an_upstream_context_overflow_is_recognised_on_every_leg_that_reports_one(
    case: str, body: str
) -> None:
    """The recorded wordings, each as it really arrived. Spec §5.5.1.

    These three prove the recorded corpus is covered. They do **not** isolate the predicates — the Anthropic-leg body carries all three signals at once — which is what the single-signal cases below are for.
    """
    info = describe(_overflow_rejection(body), source_format="openai-responses")

    assert info.condition is ErrorCondition.CONTEXT_WINDOW_EXCEEDED, case
    # The category is still decided by the status, and the condition does not touch it.
    assert info.category is ErrorCategory.CLIENT
    assert info.status_code == 400


@pytest.mark.parametrize(
    "predicate, body",
    [
        ("upstream's own code", ONLY_THE_CODE),
        ("the responses leg's fragment", ONLY_THE_FRAGMENT),
        ("the anthropic counted wording", ONLY_THE_ANTHROPIC_COUNTS),
        ("the chat-completions counted wording", ONLY_THE_CHAT_COMPLETIONS_COUNTS),
    ],
)
def test_each_predicate_the_spec_names_recognises_the_condition_on_its_own(
    predicate: str, body: str
) -> None:
    """One signal per case, so that deleting any one predicate fails exactly one of these.

    The fourth case is the one the first version of this file got wrong in the other direction: `prompt_limit_counts` read `(13613, 12288)` out of that sentence while `is_context_window_exceeded` said it was not an overflow — two functions fifteen lines apart disagreeing about the same words.
    """
    info = describe(_overflow_rejection(body), source_format="openai-responses")

    assert info.condition is ErrorCondition.CONTEXT_WINDOW_EXCEEDED, predicate


@pytest.mark.parametrize(
    "case, body",
    [
        ("unrelated failure, same upstream code", RESPONSES_LEG_UNRELATED),
        ("the bare phrase with nothing to corroborate it", BARE_PHRASE_ONLY),
    ],
)
def test_what_the_predicate_deliberately_does_not_accept(case: str, body: str) -> None:
    """Two controls. Without the first, the predicate could be `code == "invalid_request_body"` and every case above would still pass.

    The second pins a decision rather than an accident: the bare phrase is *not* a sufficient signal, because upstream echoes request-derived text into `error.message` — a tool name, an id, both recorded.

    What this does **not** buy is worth stating, because writing this test is how it was noticed: upstream's sentence is still quoted into `message` verbatim, so a client keying on that phrase acts on it either way. Declining to recognise the condition keeps this proxy from *asserting* an overflow — no restatement, no `model_max_prompt_tokens_exceeded`, upstream's real complaint intact — and that is the whole of what it keeps. Spec §5.5.1 records the residual.
    """
    info = describe(_overflow_rejection(body), source_format="openai-responses")

    assert info.condition is None, case
    # Quoted rather than restated, which is what the prefix marks, and the category's own code rather than the condition's.
    assert info.message.startswith("upstream returned")
    assert info.code == DEFAULT_CODE_FOR_CATEGORY[ErrorCategory.CLIENT]


@pytest.mark.parametrize(
    "status, expected",
    [
        # Every 4xx this proxy calls `CLIENT` can carry an overflow. 413 is the one upstream might plausibly use and nothing here depends on 400 in particular — a mutation adding a `status == 400` gate left 302 tests green.
        (400, ErrorCondition.CONTEXT_WINDOW_EXCEEDED),
        (413, ErrorCondition.CONTEXT_WINDOW_EXCEEDED),
        (422, ErrorCondition.CONTEXT_WINDOW_EXCEEDED),
        # And these cannot, whatever the body says. A 429 restated as an overflow is the worst case in the set: the client acts on the phrase with no status gate of its own, so it would compact and resend immediately — the one thing not to do when rate limited.
        (429, None),
        (401, None),
        (403, None),
        (500, None),
    ],
)
def test_only_a_client_error_can_be_an_overflow_whatever_the_body_says(
    status: int, expected: ErrorCondition | None
) -> None:
    """Spec §5.5.1's second half. The body is one question and the status is another, and this is where the second is asked."""
    info = describe(
        _overflow_rejection(ANTHROPIC_LEG_OVERFLOW, status=status),
        source_format="openai-responses",
    )

    assert info.condition is expected


def test_the_counts_are_upstreams_own_or_are_not_there_at_all() -> None:
    """Spec §5.5.2's prohibition, stated as two assertions because one of them is about an absence.

    The limit is reachable from the model catalogue and the current count is reachable from a local estimator, so a version of this that fills the numbers in is easy to write and is forbidden: the client extracts them from this sentence and shows them to a user as measurements.
    """
    stated = describe(
        _overflow_rejection(ANTHROPIC_LEG_OVERFLOW), source_format="anthropic-messages"
    )
    assert stated.message == "prompt is too long: 1051542 tokens > 1000000 maximum"

    silent = describe(
        _overflow_rejection(RESPONSES_LEG_OVERFLOW), source_format="openai-responses"
    )
    assert silent.message == "prompt is too long: the input exceeds this model's context window"
    assert not any(character.isdigit() for character in silent.message)


def test_a_restated_condition_drops_the_prefix_that_marks_a_quotation() -> None:
    """`upstream returned 400: ` in front of a restatement would be this proxy attributing its own words to upstream, and the status it repeats is already on the response."""
    info = describe(_overflow_rejection(RESPONSES_LEG_OVERFLOW), source_format="openai-responses")

    assert "upstream returned" not in info.message


def test_proxy_prompt_admission_uses_the_same_condition_without_impersonating_upstream() -> None:
    error = _prompt_limit_exceeded()
    info = describe(error, source_format="openai-responses")

    assert classify(error) is Disposition.ABORT
    assert reason_for(error) is None
    assert info.category is ErrorCategory.CLIENT
    assert info.condition is ErrorCondition.CONTEXT_WINDOW_EXCEEDED
    assert info.status_code == 400
    assert info.message == "prompt is too long: the input exceeds this model's context window"
    assert not any(character.isdigit() for character in info.message)
    assert info.param == "input[2].content[0].text"
    assert info.source_format == ""
    assert info.source_bytes == b""
    assert info.headers == {}


def test_proxy_prompt_admission_has_the_complete_shape_in_each_client_dialect() -> None:
    info = describe(_prompt_limit_exceeded())

    assert write_error(info, wire_format="openai-responses") == {
        "error": {
            "message": "prompt is too long: the input exceeds this model's context window",
            "type": "invalid_request_error",
            "param": "input[2].content[0].text",
            "code": "context_length_exceeded",
        }
    }
    assert write_error(info, wire_format="anthropic-messages") == {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "prompt is too long: the input exceeds this model's context window",
            "code": "model_max_prompt_tokens_exceeded",
            "param": "input[2].content[0].text",
        },
    }


# The spec's per-dialect table, transcribed by hand and *not* read off the production mapping. Written as expected wire output rather than as table entries, so it fails for a wrong value and for a writer that stops consulting the table alike — a reviewer changed the OpenAI spelling to nonsense and 302 tests stayed green.
CONDITION_CODE_CASES: tuple[tuple[str, str | None], ...] = (
    ("anthropic-messages", "model_max_prompt_tokens_exceeded"),
    ("openai-chat-completions", "context_length_exceeded"),
    ("openai-responses", "context_length_exceeded"),
    ("openai-embeddings", "context_length_exceeded"),
    # Google's error object has no string identifier — `code` is the HTTP status — so the expectation is an absence rather than a spelling.
    ("gemini-generate-content", None),
)


@pytest.mark.parametrize("wire_format, expected", CONDITION_CODE_CASES)
def test_each_dialect_spells_the_condition_the_way_the_spec_says(
    wire_format: str, expected: str | None
) -> None:
    info = describe(_overflow_rejection(RESPONSES_LEG_OVERFLOW), source_format="openai-responses")

    body = write_error(info, wire_format=wire_format)
    detail = cast(dict[str, object], body["error"])

    if expected is None:
        assert detail["code"] == info.status_code
    else:
        assert detail["code"] == expected


def test_the_dialect_code_cases_cover_every_wire_format() -> None:
    """The transcription is only an oracle if a missing row fails. Adding a `WireFormat` member without a row here is what this catches."""
    assert {case[0] for case in CONDITION_CODE_CASES} == {member.value for member in WireFormat}


@pytest.mark.parametrize(
    "name, table",
    [("anthropic", ANTHROPIC_CONDITION_CODES), ("openai", OPENAI_CONDITION_CODES)],
)
def test_every_dialect_that_has_a_code_spells_every_condition(
    name: str, table: dict[ErrorCondition, str]
) -> None:
    """Same failure mode as the category tables, one enum over. A condition with no spelling silently renders as its category's default, which reads as "we did not recognise this"."""
    assert set(table) == set(ErrorCondition), (
        f"{name} is missing {set(ErrorCondition) - set(table)}"
    )


def test_the_condition_table_accounts_for_every_wire_format() -> None:
    """Keyed on `WireFormat` rather than on a literal list, which is the difference between this and the version it replaces.

    Gemini's absence is an entry, not an omission: its error object's `code` is the HTTP status and its identifier is `status`, which the category already supplies. Spelling that out as a named exclusion is what makes a *new* dialect fail here instead of silently losing its condition spelling — the exact shape that once left `FORMAT_ENDPOINTS` a member short.
    """
    no_code_field = {WireFormat.GEMINI_GENERATE_CONTENT.value}

    assert set(CONDITION_CODES_BY_FORMAT) | no_code_field == {
        member.value for member in WireFormat
    }
    assert set(CONDITION_CODES_BY_FORMAT) & no_code_field == set()


def test_every_wire_format_can_be_spelled() -> None:
    """The guard `write_error`'s docstring claimed for a day and did not have.

    It says the Anthropic fallback is unreachable because every `WireFormat` has a writer. Nothing asserted that: `formats_with_writers` had no caller at all, so the sentence was a promise about a test that did not exist — and this change made it load-bearing by adding a second table on the same key.
    """
    assert formats_with_writers() == {member.value for member in WireFormat}


def test_an_unknown_dialect_gets_anthropics_shape_and_anthropics_vocabulary() -> None:
    """The fallback's own property, which is not the same as the fallback existing.

    Unreachable today — every `WireFormat` has a writer and the test above pins that — so this is asked directly rather than through a route. It is worth asking because the shape and the vocabulary can come apart: handing the caller's unknown name to the Anthropic writer produces an envelope that says it is Anthropic's while looking the condition up under a dialect with no row, and the one spelling an Anthropic client reads goes missing. That version passed every other assertion in this file.
    """
    info = describe(_overflow_rejection(RESPONSES_LEG_OVERFLOW), source_format="openai-responses")

    body = write_error(info, wire_format="some-future-dialect")
    detail = cast(dict[str, object], body["error"])

    assert body["type"] == "error"
    assert detail["code"] == "model_max_prompt_tokens_exceeded"
