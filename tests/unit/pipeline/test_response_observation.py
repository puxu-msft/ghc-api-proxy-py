from copy import deepcopy
from typing import cast

import orjson
import pytest

from app.pipeline.delivery.formats.openai_responses_passthrough import requires_client_action
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.response_action import (
    ClientActionBasis,
    ClientActionRequirement,
    classify_responses_client_action,
)
from app.pipeline.response_observation import (
    FrozenJsonArray,
    FrozenJsonObject,
    JsonAvailability,
    ResponseAvailability,
    ResponsesObserver,
    freeze_json,
    thaw_json,
)
from app.protocols.responses_anthropic import convert_responses_usage


@pytest.mark.parametrize(
    ("item", "requirement", "basis", "delivery_required"),
    [
        (
            {"type": "function_call"},
            ClientActionRequirement.REQUIRED,
            ClientActionBasis.KNOWN_CLIENT_ACTION,
            True,
        ),
        (
            {"type": "web_search_call"},
            ClientActionRequirement.NOT_REQUIRED,
            ClientActionBasis.KNOWN_SERVER_ACTION,
            False,
        ),
        (
            {"type": "tool_search_call", "execution": "client"},
            ClientActionRequirement.REQUIRED,
            ClientActionBasis.EXECUTION_CLIENT,
            True,
        ),
        (
            {"type": "tool_search_call", "execution": "server"},
            ClientActionRequirement.NOT_REQUIRED,
            ClientActionBasis.EXECUTION_SERVER,
            False,
        ),
        (
            {"type": "tool_search_call"},
            ClientActionRequirement.UNKNOWN,
            ClientActionBasis.EXECUTION_UNRECOGNIZED,
            False,
        ),
        (
            {"type": "shell_call"},
            ClientActionRequirement.REQUIRED,
            ClientActionBasis.LOCAL_SHELL_DEFAULT,
            True,
        ),
        (
            {"type": "shell_call", "environment": {"type": "container_reference"}},
            ClientActionRequirement.NOT_REQUIRED,
            ClientActionBasis.CONTAINER_EXECUTION,
            False,
        ),
        (
            {"type": "shell_call", "environment": {"type": "local"}},
            ClientActionRequirement.REQUIRED,
            ClientActionBasis.LOCAL_SHELL_ENVIRONMENT,
            True,
        ),
        (
            {"type": "some_2027_tool_call"},
            ClientActionRequirement.UNKNOWN,
            ClientActionBasis.UNKNOWN_TYPE_FALLBACK,
            True,
        ),
        (
            {},
            ClientActionRequirement.UNKNOWN,
            ClientActionBasis.UNKNOWN_TYPE_FALLBACK,
            True,
        ),
    ],
)
def test_client_action_policy_preserves_observation_and_delivery_answers(
    item: dict[str, object],
    requirement: ClientActionRequirement,
    basis: ClientActionBasis,
    delivery_required: bool,
) -> None:
    observed = classify_responses_client_action(item)

    assert observed.requirement is requirement
    assert observed.basis is basis
    assert observed.delivery_required is delivery_required
    # This assertion is intentionally against the fixed table above as well as the shared classifier. Merely comparing the adapter with the classifier would leave both free to drift together.
    assert requires_client_action(item) is delivery_required


@pytest.mark.parametrize(
    "item_type",
    [
        "function_call",
        "custom_tool_call",
        "computer_call",
        "local_shell_call",
        "apply_patch_call",
        "mcp_approval_request",
    ],
)
def test_every_known_client_action_type_is_pinned(item_type: str) -> None:
    observed = classify_responses_client_action({"type": item_type})

    assert observed.requirement is ClientActionRequirement.REQUIRED
    assert observed.basis is ClientActionBasis.KNOWN_CLIENT_ACTION
    assert observed.delivery_required is True


@pytest.mark.parametrize(
    "item_type",
    [
        "web_search_call",
        "file_search_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "reasoning",
        "message",
    ],
)
def test_every_known_server_action_type_is_pinned(item_type: str) -> None:
    observed = classify_responses_client_action({"type": item_type})

    assert observed.requirement is ClientActionRequirement.NOT_REQUIRED
    assert observed.basis is ClientActionBasis.KNOWN_SERVER_ACTION
    assert observed.delivery_required is False


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"x": 1},
        [["x", 1]],
        {"empty_object": {}, "empty_array": [], "nested": [{"x": [True, None, 1.5]}]},
    ],
)
def test_frozen_json_round_trips_without_object_array_collisions(value: object) -> None:
    frozen = freeze_json(value)

    assert thaw_json(frozen) == value


def test_frozen_json_tags_empty_object_and_array_differently() -> None:
    assert isinstance(freeze_json({}), FrozenJsonObject)
    assert isinstance(freeze_json([]), FrozenJsonArray)
    assert freeze_json({}) != freeze_json([])
    assert freeze_json({"x": 1}) != freeze_json([["x", 1]])


def test_frozen_json_preserves_bool_as_a_bool_not_an_equal_integer() -> None:
    restored_bool = thaw_json(freeze_json(True))
    restored_integer = thaw_json(freeze_json(1))

    assert restored_bool is True
    assert type(restored_bool) is bool
    assert restored_integer == 1
    assert type(restored_integer) is int


def test_frozen_json_preserves_provider_integers_beyond_javascript_precision() -> None:
    value = 2**53

    assert thaw_json(freeze_json(value)) == value


def test_stream_decoder_preserves_arbitrary_precision_provider_integers() -> None:
    value = 10**100
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=(
                '{"type":"response.completed","copilot_usage":{"opaque":'
                f"{value}"
                '},"response":{"status":"completed","usage":{"input_tokens":'
                f"{value}"
                ',"input_tokens_details":{"cached_tokens":0,"cache_write_tokens":0},'
                '"output_tokens":1,"total_tokens":'
                f"{value + 1}"
                "}}}"
            ),
        )
    )

    observed = observer.snapshot()

    assert observed.usage is not None
    assert observed.usage.normalized.input_tokens == value
    assert observed.usage.exact is not None
    assert observed.usage.exact.upstream_input_tokens == value
    assert observed.usage.raw.value is not None
    raw = thaw_json(observed.usage.raw.value)
    assert isinstance(raw, dict)
    assert type(raw["input_tokens"]) is int
    assert raw["input_tokens"] == value
    assert observed.provider_usage.value is not None
    provider_usage = thaw_json(observed.provider_usage.value)
    assert isinstance(provider_usage, dict)
    assert type(provider_usage["opaque"]) is int
    assert provider_usage["opaque"] == value


def test_frozen_json_is_detached_from_the_producer() -> None:
    source = {"items": [{"value": 1}]}
    frozen = freeze_json(source)

    source["items"][0]["value"] = 2
    source["items"].append({"value": 3})

    assert thaw_json(frozen) == {"items": [{"value": 1}]}


def _response_body() -> dict[str, object]:
    return {
        "status": "completed",
        "model": "gpt-5.5-2026-04-23",
        "service_tier": "default",
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "reasoning",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": "brief"}],
                "encrypted_content": "sealed",
            },
            {
                "type": "function_call",
                "status": "completed",
                "name": "Bash",
                "call_id": "call_1",
            },
        ],
        "usage": {
            "input_tokens": 4693,
            "input_tokens_details": {"cached_tokens": 3712, "cache_write_tokens": 0},
            "output_tokens": 112,
            "output_tokens_details": {"reasoning_tokens": 51},
            "total_tokens": 4805,
        },
        "copilot_usage": {"total_nano_aiu": 1012100000},
        "tool_usage": {"web_search": {"num_requests": 1}},
    }


def test_observer_preserves_responses_facts_and_exact_usage() -> None:
    body = _response_body()
    observer = ResponsesObserver()

    observer.observe_response(body)
    observed = observer.snapshot()

    assert observed.availability is ResponseAvailability.OBSERVED
    assert observed.terminal_event_type == "response.completed"
    assert observed.terminal_seen is True
    assert observed.status == "completed"
    assert observed.model == "gpt-5.5-2026-04-23"
    assert observed.service_tier == "default"
    assert observed.output_items is not None
    assert [item.type for item in observed.output_items] == [
        "web_search_call",
        "reasoning",
        "function_call",
    ]
    assert observed.output_items[0].status == "completed"
    assert observed.output_items[0].client_action.requirement is ClientActionRequirement.NOT_REQUIRED
    assert observed.output_items[0].client_action.basis is ClientActionBasis.KNOWN_SERVER_ACTION
    assert observed.output_items[0].client_action.delivery_required is False
    assert observed.output_items[1].reasoning.summary_items == 1
    assert observed.output_items[1].reasoning.has_readable_summary is True
    assert observed.output_items[1].reasoning.has_encrypted_content is True
    assert observed.output_items[2].status == "completed"
    assert observed.output_items[2].name == "Bash"
    assert observed.output_items[2].call_id == "call_1"
    assert observed.output_items[2].client_action.requirement is ClientActionRequirement.REQUIRED
    assert observed.output_items[2].client_action.basis is ClientActionBasis.KNOWN_CLIENT_ACTION
    assert observed.output_items[2].client_action.delivery_required is True

    usage = observed.usage
    assert usage is not None
    assert usage.normalized.input_tokens == 981
    assert usage.normalized.cache_read_input_tokens == 3712
    assert usage.normalized.cache_creation_input_tokens == 0
    assert usage.normalized.output_tokens == 112
    assert usage.exact is not None
    assert usage.exact.upstream_input_tokens == 4693
    assert usage.exact.reasoning_tokens == 51
    assert usage.exact.computed_total_tokens == 4805
    assert usage.exact.upstream_total_tokens == 4805
    assert thaw_json(usage.exact.input_tokens_details) == {
        "cached_tokens": 3712,
        "cache_write_tokens": 0,
    }
    assert thaw_json(usage.exact.output_tokens_details) == {"reasoning_tokens": 51}
    assert usage.raw.availability is JsonAvailability.OBSERVED
    assert usage.raw.value is not None
    assert thaw_json(usage.raw.value) == body["usage"]
    assert observed.provider_usage.value is not None
    assert thaw_json(observed.provider_usage.value) == {"total_nano_aiu": 1012100000}
    assert observed.tool_usage.value is not None
    assert thaw_json(observed.tool_usage.value) == {"web_search": {"num_requests": 1}}


def test_stream_terminal_and_buffered_body_have_the_same_observation() -> None:
    body = _response_body()
    buffered = ResponsesObserver()
    streamed = ResponsesObserver()

    buffered.observe_response(body)
    envelope = {
        "copilot_usage": body["copilot_usage"],
        "response": body,
        "type": "response.completed",
    }
    streamed.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps(envelope).decode(),
        )
    )

    assert streamed.snapshot() == buffered.snapshot()


def test_terminal_output_upserts_by_output_index_not_item_id() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.added",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"id": "opening", "type": "function_call", "name": "before"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"id": "closing", "type": "function_call", "name": "after"},
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert len(items) == 1
    assert items[0].name == "after"


def test_malformed_usage_is_an_issue_not_an_observer_exception() -> None:
    observer = ResponsesObserver()

    observer.observe_response({
        "status": "completed",
        "usage": {"input_tokens": "not-an-integer", "output_tokens": 1},
    })
    observed = observer.snapshot()

    assert observed.availability is ResponseAvailability.OBSERVED
    assert observed.usage is not None
    assert observed.usage.exact is None
    assert observed.usage.normalized.input_tokens is None
    assert observed.usage.raw.availability is JsonAvailability.OBSERVED
    assert observed.usage.issues


def test_usage_absent_explicit_null_and_explicit_zero_remain_distinct() -> None:
    absent = ResponsesObserver()
    explicit_null = ResponsesObserver()
    explicit_zero = ResponsesObserver()

    absent.observe_response({"status": "completed"})
    explicit_null.observe_response({"status": "completed", "usage": None})
    explicit_zero.observe_response({
        "status": "completed",
        "usage": {
            "input_tokens": 0,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 0,
        },
    })

    absent_usage = absent.snapshot().usage
    null_usage = explicit_null.snapshot().usage
    zero_usage = explicit_zero.snapshot().usage
    assert absent_usage is not None
    assert null_usage is not None
    assert zero_usage is not None
    assert absent_usage.raw.availability is JsonAvailability.ABSENT
    assert null_usage.raw.availability is JsonAvailability.EXPLICIT_NULL
    assert zero_usage.raw.availability is JsonAvailability.OBSERVED
    assert absent_usage.normalized.cache_read_input_tokens is None
    assert null_usage.normalized.cache_read_input_tokens is None
    assert zero_usage.normalized.cache_read_input_tokens == 0
    assert zero_usage.exact is not None
    assert zero_usage.exact.reasoning_tokens == 0


@pytest.mark.parametrize(
    "event",
    [
        SseEvent(
            event="error",
            data='{"type":"error","error":{"code":"broken","message":"boom"}}',
        ),
        SseEvent(
            event="response.output_item.added",
            data='{"output_index":0,"item":{"type":"message"}}',
        ),
    ],
)
def test_any_observed_event_without_usage_still_has_an_absent_usage_dto(
    event: SseEvent,
) -> None:
    observer = ResponsesObserver()
    observer.observe_event(event)

    observed = observer.snapshot()

    assert observed.availability is ResponseAvailability.OBSERVED
    assert observed.usage is not None
    assert observed.usage.raw.availability is JsonAvailability.ABSENT
    assert observed.usage.exact is None
    assert observed.usage.normalized.input_tokens is None


def test_unavailable_attempt_observation_names_that_no_provider_body_was_seen() -> None:
    observed = ResponsesObserver().snapshot()

    assert observed.availability is ResponseAvailability.UNAVAILABLE
    assert [issue.code for issue in observed.issues] == [
        "provider_body_not_observed"
    ]
    assert observed.issues[0].field_path == "response"


def test_provider_error_summary_is_bounded_once_while_raw_error_stays_exact() -> None:
    message = "first\nsecond " + "x" * 300
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "error": {
            "type": "server_error",
            "code": "provider_broke",
            "message": message,
        },
    })

    observed = observer.snapshot()

    assert observed.error_summary is not None
    assert observed.error_summary.type == "server_error"
    assert observed.error_summary.code == "provider_broke"
    assert observed.error_summary.message is not None
    assert "\n" not in observed.error_summary.message
    assert observed.error_summary.message.endswith("more chars)")
    assert observed.error.value is not None
    assert thaw_json(observed.error.value) == {
        "type": "server_error",
        "code": "provider_broke",
        "message": message,
    }


def test_provider_error_summary_bounds_type_and_code_as_well_as_message() -> None:
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "error": {
            "type": "t" * 300,
            "code": "c" * 300,
            "message": "m" * 300,
        },
    })

    summary = observer.snapshot().error_summary

    assert summary is not None
    assert summary.type is not None and summary.type.endswith("more chars)")
    assert summary.code is not None and summary.code.endswith("more chars)")
    assert summary.message is not None and summary.message.endswith("more chars)")


@pytest.mark.parametrize(
    ("body", "issue"),
    [
        (b"", "response_body_not_json"),
        (b"not-json", "response_body_not_json"),
        (b"[]", "response_body_not_object"),
    ],
)
def test_buffered_unreadable_body_has_a_specific_unavailable_issue(
    body: bytes,
    issue: str,
) -> None:
    observer = ResponsesObserver()

    observer.observe_body_bytes(body)
    observed = observer.snapshot()

    assert observed.availability is ResponseAvailability.UNAVAILABLE
    assert [item.code for item in observed.issues] == [issue]
    assert observed.usage is None


def test_missing_usage_details_remain_unknown_in_exact_and_normalized_facts() -> None:
    observer = ResponsesObserver()

    observer.observe_response({
        "status": "completed",
        "usage": {"input_tokens": 9, "output_tokens": 2},
    })
    usage = observer.snapshot().usage

    assert usage is not None
    assert usage.normalized.input_tokens is None
    assert usage.normalized.cache_read_input_tokens is None
    assert usage.normalized.cache_creation_input_tokens is None
    assert usage.exact is not None
    assert usage.exact.input_tokens is None
    assert usage.exact.cache_read_input_tokens is None
    assert usage.exact.cache_creation_input_tokens is None
    assert usage.exact.reasoning_tokens is None
    # The legacy wire still has the concrete zeros Anthropic requires; absence is retained only in the exact observation.
    converted = convert_responses_usage({"input_tokens": 9, "output_tokens": 2})
    assert converted.wire.cache_read_input_tokens == 0
    assert converted.wire.cache_creation_input_tokens == 0


@pytest.mark.parametrize(
    "input_details",
    [
        {"cached_tokens": 4},
        {"cache_write_tokens": 3},
    ],
)
def test_fresh_input_stays_unknown_when_either_cache_detail_is_missing(
    input_details: dict[str, int],
) -> None:
    observer = ResponsesObserver()

    observer.observe_response({
        "status": "completed",
        "usage": {
            "input_tokens": 9,
            "input_tokens_details": input_details,
            "output_tokens": 2,
        },
    })
    usage = observer.snapshot().usage

    assert usage is not None
    assert usage.normalized.input_tokens is None
    assert usage.exact is not None
    assert usage.exact.input_tokens is None


def test_bool_output_index_is_rejected_without_colliding_with_integer_one() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": True,
                "item": {"type": "function_call", "name": "bool"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 1,
                "item": {"type": "function_call", "name": "integer"},
            }).decode(),
        )
    )

    observed = observer.snapshot()
    assert observed.output_items is not None
    assert [(item.output_index, item.name) for item in observed.output_items] == [(1, "integer")]
    assert "invalid_output_index" in [issue.code for issue in observed.issues]


def test_terminal_item_cannot_be_overwritten_by_a_late_partial_event() -> None:
    observer = ResponsesObserver()
    body = {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": "terminal-name",
                "call_id": "terminal-call",
                "status": "completed",
            }
        ],
    }
    observer.observe_event(
        SseEvent(
            event="response.output_item.added",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"type": "function_call", "name": "added-name"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"type": "function_call", "name": "done-name"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps({"response": body}).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.output_item.added",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"type": "function_call", "name": "late-partial"},
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert len(items) == 1
    assert items[0].name == "terminal-name"
    assert items[0].call_id == "terminal-call"
    assert items[0].status == "completed"


def test_terminal_explicit_unknown_execution_overrides_older_known_action() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {
                    "type": "tool_search_call",
                    "execution": "client",
                },
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps({
                "response": {
                    "status": "completed",
                    "output": [
                        {
                            "type": "tool_search_call",
                            "execution": "future",
                        }
                    ],
                }
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert items[0].execution == "future"
    assert items[0].client_action.requirement is ClientActionRequirement.UNKNOWN
    assert items[0].client_action.basis is ClientActionBasis.EXECUTION_UNRECOGNIZED
    assert items[0].client_action.delivery_required is False


def test_terminal_unknown_type_overrides_an_older_known_type() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"type": "function_call", "name": "old"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps({
                "response": {
                    "status": "completed",
                    "output": [{"type": "some_2027_tool_call", "name": "new"}],
                }
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert items[0].type == "some_2027_tool_call"
    assert items[0].name == "new"
    assert items[0].client_action.requirement is ClientActionRequirement.UNKNOWN
    assert items[0].client_action.basis is ClientActionBasis.UNKNOWN_TYPE_FALLBACK
    assert items[0].client_action.delivery_required is True


def test_terminal_missing_execution_keeps_the_explicit_earlier_fact() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {"type": "tool_search_call", "execution": "client"},
            }).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps({
                "response": {
                    "status": "completed",
                    "output": [{"type": "tool_search_call"}],
                }
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert items[0].execution == "client"
    assert items[0].client_action.requirement is ClientActionRequirement.REQUIRED
    assert items[0].client_action.basis is ClientActionBasis.EXECUTION_CLIENT
    assert items[0].client_action.delivery_required is True


@pytest.mark.parametrize(
    (
        "older_item",
        "terminal_item",
        "expected_type",
        "expected_execution",
        "expected_basis",
        "expected_delivery",
    ),
    [
        (
            {"type": "tool_search_call", "execution": "client"},
            {"type": "tool_search_call", "execution": None},
            "tool_search_call",
            None,
            ClientActionBasis.EXECUTION_UNRECOGNIZED,
            False,
        ),
        (
            {"type": "function_call", "name": "old"},
            {"type": None, "name": "new"},
            None,
            None,
            ClientActionBasis.UNKNOWN_TYPE_FALLBACK,
            True,
        ),
        (
            {"type": "function_call", "name": "old"},
            {"type": 42, "name": "new"},
            None,
            None,
            ClientActionBasis.UNKNOWN_TYPE_FALLBACK,
            True,
        ),
        (
            {"type": "tool_search_call", "execution": "client"},
            {"execution": "future"},
            "tool_search_call",
            "future",
            ClientActionBasis.EXECUTION_UNRECOGNIZED,
            False,
        ),
    ],
)
def test_terminal_item_presence_and_action_are_derived_from_one_merged_draft(
    older_item: dict[str, object],
    terminal_item: dict[str, object],
    expected_type: str | None,
    expected_execution: str | None,
    expected_basis: ClientActionBasis,
    expected_delivery: bool,
) -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({"output_index": 0, "item": older_item}).decode(),
        )
    )
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=orjson.dumps({
                "response": {
                    "status": "completed",
                    "output": [terminal_item],
                }
            }).decode(),
        )
    )

    items = observer.snapshot().output_items
    assert items is not None
    assert items[0].type == expected_type
    assert items[0].execution == expected_execution
    assert items[0].client_action.requirement is ClientActionRequirement.UNKNOWN
    assert items[0].client_action.basis is expected_basis
    assert items[0].client_action.delivery_required is expected_delivery


def test_irrelevant_item_extensions_do_not_enter_or_poison_the_summary_draft() -> None:
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.output_item.done",
            data=orjson.dumps({
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "name": "Bash",
                    "arguments": "full-tool-arguments",
                    "content": [{"type": "output_text", "text": "full-output-text"}],
                    "future_extension": 2**53,
                },
            }).decode(),
        )
    )

    observed = observer.snapshot()
    assert observed.output_items is not None
    assert len(observed.output_items) == 1
    assert observed.output_items[0].type == "function_call"
    assert observed.output_items[0].name == "Bash"
    assert observed.output_items[0].client_action.requirement is ClientActionRequirement.REQUIRED
    assert "full-tool-arguments" not in repr(observer)
    assert "full-output-text" not in repr(observer)
    assert "output_item_unreadable" not in [issue.code for issue in observed.issues]


def test_invalid_event_payload_is_recorded_without_raising() -> None:
    observer = ResponsesObserver()

    observer.observe_event(SseEvent(event="response.completed", data="{"))
    observed = observer.snapshot()

    assert observed.availability is ResponseAvailability.UNAVAILABLE
    assert observed.terminal_seen is None
    assert [issue.code for issue in observed.issues] == ["event_observation_failed"]


def test_begin_attempt_replaces_the_current_response_observation_before_send() -> None:
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="model",
        payload={},
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    first = context.begin_attempt()
    assert first.response_observer is not None
    first.response_observer.observe_response(_response_body())
    context.response_observation = first.response_observer.snapshot()

    second = context.begin_attempt()

    assert second.response_observer is not None
    assert second.response_observer is not first.response_observer
    assert context.response_observation is None
    assert second.response_observer.snapshot().availability is ResponseAvailability.UNAVAILABLE


def test_public_usage_conversion_remains_the_single_projection() -> None:
    raw = cast_usage(_response_body()["usage"])

    converted = convert_responses_usage(raw)

    assert converted.wire.input_tokens == 981
    assert converted.wire.cache_read_input_tokens == 3712
    assert converted.wire.cache_creation_input_tokens == 0
    assert converted.wire.output_tokens == 112
    assert converted.exact is not None
    assert converted.exact.reasoning_tokens == 51


def cast_usage(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return deepcopy(cast(dict[str, object], value))
