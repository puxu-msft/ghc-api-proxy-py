import json
from typing import Any
from unittest.mock import patch

import pytest
from openai.lib.streaming.chat._completions import ChatCompletionStreamState
from openai.types.chat import ChatCompletionChunk
from starlette.responses import JSONResponse

from app.pipeline.chat_completions import (
    ChatAttemptState,
    ChatCompletionUnassemblable,
    ChatEventReader,
)
from app.pipeline.delivery.sse_source import RawSseFrame
from app.pipeline.response_observation import (
    FrozenJsonArray,
    FrozenJsonObject,
    JsonAvailability,
    thaw_json,
)


def _frame(
    value: object,
    ordinal: int,
    *,
    event: str = "",
    start: int = 0,
) -> RawSseFrame:
    data = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    event_line = f"event: {event}\n" if event else ""
    raw = f"{event_line}data: {data}\n\n".encode()
    separator_start = len(raw) - 2
    return RawSseFrame(
        raw=raw,
        body_end=separator_start,
        start=start,
        end=start + len(raw),
        ordinal=ordinal,
        terminated=True,
    )


def _observe(state: ChatAttemptState, value: object, ordinal: int, *, event: str = "") -> None:
    facts = state.read(_frame(value, ordinal, event=event))
    before = state.held_bytes
    delta = state.additional_held_bytes(facts)
    state.observe(facts)
    assert state.held_bytes == before + delta


def test_finish_reason_without_done_is_not_a_complete_sse_transaction() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-1",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": "complete text"}, "finish_reason": "stop"}],
        },
        0,
    )

    snapshot = state.observation_facts()

    assert snapshot.done_seen is False
    assert snapshot.choices[0].finish_reason.value == "stop"
    with pytest.raises(ChatCompletionUnassemblable, match=r"without \[DONE\]"):
        state.to_completion_payload()


def test_first_done_freezes_semantics_while_later_frames_remain_outside_state() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "before"}, "finish_reason": "stop"}],
        },
        0,
    )
    _observe(state, "[DONE]", 1)
    frozen = state.observation_facts()
    payload = state.to_completion_payload()

    _observe(
        state,
        {
            "id": "chatcmpl-other",
            "created": 2,
            "model": "other",
            "choices": [{"index": 0, "delta": {"content": " after"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 999},
        },
        2,
    )

    assert frozen.semantic_end_offset == _frame("[DONE]", 1).end
    assert state.observation_facts() == frozen
    assert state.to_completion_payload() == payload
    assert payload["choices"][0]["message"]["content"] == "before"


def test_standard_projection_preserves_all_choices_tool_order_duplicates_usage_and_unknowns() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 123,
            "model": "model-a",
            "service_tier": "default",
            "future_top": {"a": 1},
            "choices": [
                {
                    "index": 1,
                    "delta": {"content": "second", "future_delta": "kept"},
                    "finish_reason": None,
                    "future_choice": True,
                },
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "reasoning_content": "think",
                        "content": "hel",
                        "tool_calls": [
                            {
                                "index": 2,
                                "id": "call-2",
                                "type": "function",
                                "function": {"name": "Bash", "arguments": "{\"x\":", "future_function": 2},
                                "future_tool": "kept",
                            },
                            {"index": 0, "id": "call-0", "type": "function", "function": {"arguments": "{}"}},
                            {"index": 1, "id": "call-1", "type": "function", "function": {"name": "Bash", "arguments": ""}},
                        ],
                    },
                    "finish_reason": None,
                },
            ],
        },
        0,
    )
    _observe(
        state,
        {
            "id": "chatcmpl-1",
            "created": 123,
            "model": "model-a",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": "lo",
                        "tool_calls": [
                            {"index": 2, "function": {"arguments": "1}"}},
                            {"index": 2, "function": {"arguments": ""}},
                        ],
                    },
                    "finish_reason": "tool_calls",
                },
                {"index": 1, "delta": dict[str, Any](), "finish_reason": "stop"},
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                "prompt_tokens_details": {"cached_tokens": 6},
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
            "future_top": {"a": 1},
        },
        1,
    )
    _observe(state, "[DONE]", 2)

    payload = state.to_completion_payload()

    assert payload == {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 123,
        "model": "model-a",
        "service_tier": "default",
        "future_top": {"a": 1},
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "hello",
                    "refusal": None,
                    "reasoning_content": "think",
                    "tool_calls": [
                        {"id": "call-0", "type": "function", "function": {"arguments": "{}"}},
                        {"id": "call-1", "type": "function", "function": {"name": "Bash", "arguments": ""}},
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"x":1}', "future_function": 2},
                            "future_tool": "kept",
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            },
            {
                "index": 1,
                "message": {
                    "role": "assistant",
                    "content": "second",
                    "refusal": None,
                    "future_delta": "kept",
                },
                "finish_reason": "stop",
                "future_choice": True,
            },
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "prompt_tokens_details": {"cached_tokens": 6},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    }
    snapshot = state.observation_facts()
    assert [choice.index for choice in snapshot.choices] == [0, 1]
    assert [tool.index for tool in snapshot.choices[0].tool_calls] == [0, 1, 2]
    assert [tool.name.value for tool in snapshot.choices[0].tool_calls] == [None, "Bash", "Bash"]
    assert snapshot.usage is not None
    assert snapshot.usage.normalized.input_tokens == 4
    assert snapshot.usage.normalized.cache_read_input_tokens == 6
    assert snapshot.usage.exact is not None
    assert snapshot.usage.exact.reasoning_tokens == 2
    assert thaw_json(snapshot.top_level_unknown) == {"future_top": {"a": 1}}
    assert thaw_json(snapshot.choices[1].choice_unknown) == {"future_choice": True}
    assert thaw_json(snapshot.choices[1].message_unknown) == {"future_delta": "kept"}
    assert any(issue.code == "duplicate_tool_index" for issue in snapshot.issues)
    assert any(issue.code == "role_synthesized" for issue in snapshot.issues)


def test_legacy_function_call_and_logprobs_are_accumulated_without_sdk_helper_fields() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-legacy",
            "created": 7,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "function_call": {"name": "lookup", "arguments": "{\"q\":"},
                    },
                    "logprobs": {"content": [{"token": "a"}], "refusal": None},
                    "finish_reason": None,
                }
            ],
        },
        0,
    )
    _observe(
        state,
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"function_call": {"arguments": "1}"}},
                    "logprobs": {"content": [{"token": "b"}], "refusal": []},
                    "finish_reason": "stop",
                }
            ]
        },
        1,
    )
    _observe(state, "[DONE]", 2)

    [choice] = state.to_completion_payload()["choices"]

    assert choice["message"]["function_call"] == {
        "name": "lookup",
        "arguments": '{"q":1}',
    }
    assert choice["logprobs"] == {
        "content": [{"token": "a"}, {"token": "b"}],
        "refusal": [],
    }
    assert "parsed" not in choice["message"]["function_call"]
    assert "parsed_arguments" not in choice["message"]["function_call"]


def test_same_unknown_object_with_different_key_order_is_not_a_conflict() -> None:
    state = ChatAttemptState()
    base: dict[str, Any] = {
        "id": "chatcmpl-1",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": dict[str, Any](), "finish_reason": "stop"}],
    }
    _observe(state, {**base, "future": {"a": 1, "b": 2}}, 0)
    _observe(state, {**base, "future": {"b": 2, "a": 1}}, 1)
    _observe(state, "[DONE]", 2)

    assert state.to_completion_payload()["future"] == {"a": 1, "b": 2}
    assert not any(issue.code == "chat_unknown_field_conflict" for issue in state.observation_facts().issues)


def test_unknown_field_conflict_is_unassemblable_but_retains_first_observation() -> None:
    state = ChatAttemptState()
    base: dict[str, Any] = {
        "id": "chatcmpl-1",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": dict[str, Any](), "finish_reason": "stop"}],
    }
    _observe(state, {**base, "future": {"v": 1}}, 0)
    _observe(state, {**base, "future": {"v": 2}}, 1)
    _observe(state, "[DONE]", 2)

    snapshot = state.observation_facts()

    assert thaw_json(snapshot.top_level_unknown) == {"future": {"v": 1}}
    assert any(issue.code == "chat_unknown_field_conflict" for issue in snapshot.issues)
    with pytest.raises(ChatCompletionUnassemblable) as caught:
        state.to_completion_payload()
    assert caught.value.field_path == "future"


def test_additional_held_bytes_accounts_for_replacement_and_usage_issue() -> None:
    state = ChatAttemptState()
    _observe(state, {"service_tier": "a-long-service-tier", "usage": {"prompt_tokens": 100}}, 0)
    facts = state.read(_frame({"service_tier": "x", "usage": {"prompt_tokens": 2}}, 1))

    delta = state.additional_held_bytes(facts)
    before = state.held_bytes
    state.observe(facts)

    assert delta == state.held_bytes - before
    assert state.held_bytes == before + delta
    snapshot = state.observation_facts()
    assert snapshot.usage is not None
    assert snapshot.usage.exact is not None
    assert snapshot.usage.exact.upstream_input_tokens == 2
    assert any(issue.code == "chat_usage_replaced" for issue in snapshot.issues)


def test_error_facts_freeze_stream_error_before_later_chunks() -> None:
    state = ChatAttemptState()
    error = {
        "error": {"code": "unknown_future_error", "message": "failed"},
        "choices": [{"index": 0, "delta": {"content": "must not become content"}}],
    }
    _observe(state, error, 0)
    frozen = state.observation_facts()
    _observe(state, {"id": "late", "created": 1, "model": "late", "choices": []}, 1)

    assert state.observation_facts() == frozen
    assert frozen.stream_error.availability is JsonAvailability.OBSERVED
    assert frozen.error_values == ("unknown_future_error",)
    assert frozen.error_retry_reason is None
    assert frozen.semantic_end_offset == _frame(error, 0).end
    assert frozen.choices == ()
    assert state.done_seen is False


def test_one_reader_instance_supplies_state_and_both_projections_without_reparse() -> None:
    class CountingReader(ChatEventReader):
        def __init__(self) -> None:
            self.calls = 0

        def read(self, frame: RawSseFrame):
            self.calls += 1
            return super().read(frame)

    reader = CountingReader()
    state = ChatAttemptState(reader=reader)
    _observe(
        state,
        {
            "id": "chatcmpl-1",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "stop"}],
        },
        0,
    )
    _observe(state, "[DONE]", 1)
    calls_after_observation = reader.calls

    state.to_completion_payload()
    state.observation_facts()
    state.projection_size_bytes()
    state.observation_size_bytes()

    assert calls_after_observation == 2
    assert reader.calls == calls_after_observation


def test_readable_non_objects_are_unassemblable_while_malformed_is_unreadable() -> None:
    reader = ChatEventReader()
    states = [ChatAttemptState(reader=reader) for _ in range(4)]
    facts = [
        reader.read(_frame("null", 0)),
        reader.read(_frame("[]", 1)),
        reader.read(_frame("{bad", 2)),
        reader.read(_frame('{"future":1e400}', 3)),
    ]

    for state, event_facts in zip(states, facts, strict=True):
        state.observe(event_facts)

    assert facts[0].value.availability is JsonAvailability.EXPLICIT_NULL
    assert facts[1].value.availability is JsonAvailability.OBSERVED
    assert facts[2].value.availability is JsonAvailability.UNREADABLE
    assert facts[3].value.availability is JsonAvailability.UNREADABLE
    assert all(state.unassemblable for state in states)


def test_large_unknown_keys_are_counted_at_every_retained_layer() -> None:
    top_key = "t" * 100_000
    tool_key = "u" * 100_000
    function_key = "f" * 100_000
    payload: dict[str, Any] = {
        top_key: "x",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            tool_key: "y",
                            "function": {function_key: "z"},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ],
    }
    state = ChatAttemptState()
    facts = state.read(_frame(payload, 10))

    delta = state.additional_held_bytes(facts)
    state.observe(facts)

    assert delta == state.held_bytes
    assert delta >= len(top_key.encode()) + len(tool_key.encode()) + len(function_key.encode())
    snapshot = state.observation_facts()
    assert thaw_json(snapshot.top_level_unknown) == {top_key: "x"}
    assert thaw_json(snapshot.choices[0].tool_calls[0].tool_unknown) == {tool_key: "y"}
    assert thaw_json(snapshot.choices[0].tool_calls[0].function_unknown) == {
        function_key: "z"
    }
    repeated = state.read(_frame(payload, 11))
    assert state.additional_held_bytes(repeated) == 0


def test_repeated_arbitrary_precision_unknown_integer_uses_recursive_equality() -> None:
    value = 10**100
    state = ChatAttemptState()
    facts = state.read(_frame({"future": value}, 0))
    state.observe(facts)

    assert state.additional_held_bytes(facts) == 0
    state.observe(facts)
    assert state.unassemblable is False
    assert thaw_json(state.observation_facts().top_level_unknown) == {"future": value}


def test_prospective_size_does_not_clone_or_materialize_the_incoming_value() -> None:
    state = ChatAttemptState()
    facts = state.read(_frame({"future": {"nested": "value"}}, 0))

    with (
        patch("copy.deepcopy", side_effect=AssertionError("state deep-copied")),
        patch(
            "app.pipeline.chat_completions.state.thaw_json",
            side_effect=AssertionError("incoming JSON materialized"),
        ),
        patch.object(
            ChatAttemptState,
            "to_completion_payload",
            side_effect=AssertionError("projection materialized"),
        ),
        patch.object(
            ChatAttemptState,
            "observation_facts",
            side_effect=AssertionError("snapshot materialized"),
        ),
    ):
        delta = state.additional_held_bytes(facts)

    assert delta > 0
    assert state.held_bytes == 0


def test_prospective_equality_indexes_only_incoming_deep_wide_unknown() -> None:
    def nested_unknown(*, reverse_keys: bool, boolean: object, ordered: list[int]) -> dict[str, object]:
        value: object = {"boolean": boolean, "ordered": ordered, "large": 10**100}
        for depth in range(24):
            entries: list[tuple[str, object]] = [
                (
                    f"wide_{depth}_{index}",
                    (
                        {"integer": 10**100 + index, "boolean": index % 2 == 0}
                        if not reverse_keys
                        else {"boolean": index % 2 == 0, "integer": 10**100 + index}
                    ),
                )
                for index in range(24)
            ]
            entries.append(("nested", value))
            if reverse_keys:
                entries.reverse()
            value = dict(entries)
        assert isinstance(value, dict)
        return value

    current_facts = ChatAttemptState().read(
        _frame({"future": nested_unknown(reverse_keys=False, boolean=True, ordered=[1, 2])}, 0)
    )
    state = ChatAttemptState()
    state.observe(current_facts)
    current_value = current_facts.value.value
    assert isinstance(current_value, FrozenJsonObject)
    current_unknown = dict(current_value.items)["future"]
    retained_item_ids: set[int] = set()

    def collect_retained_item_ids(value: object) -> None:
        if isinstance(value, FrozenJsonObject):
            retained_item_ids.add(id(value.items))
            for _, nested in value.items:
                collect_retained_item_ids(nested)
        elif isinstance(value, FrozenJsonArray):
            for nested in value.items:
                collect_retained_item_ids(nested)

    collect_retained_item_ids(current_unknown)

    class RejectCurrentItemsDict(dict[Any, Any]):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if args and id(args[0]) in retained_item_ids:
                raise AssertionError("current retained FrozenJsonObject.items copied")
            super().__init__(*args, **kwargs)

    cases = (
        (nested_unknown(reverse_keys=True, boolean=True, ordered=[1, 2]), 0),
        (nested_unknown(reverse_keys=True, boolean=1, ordered=[1, 2]), 1),
        (nested_unknown(reverse_keys=True, boolean=True, ordered=[2, 1]), 1),
    )
    for ordinal, (incoming, new_conflicts) in enumerate(cases, start=1):
        facts = state.read(_frame({"future": incoming}, ordinal))
        before = state.held_bytes
        conflicts_before = sum(
            issue.code == "chat_unknown_field_conflict" for issue in state.observation_facts().issues
        )
        with patch(
            "app.pipeline.chat_completions.state.dict",
            RejectCurrentItemsDict,
            create=True,
        ):
            delta = state.additional_held_bytes(facts)
        state.observe(facts)

        assert before + delta == state.held_bytes
        conflicts_after = sum(
            issue.code == "chat_unknown_field_conflict" for issue in state.observation_facts().issues
        )
        assert conflicts_after == conflicts_before + new_conflicts


def test_prospective_delta_replays_duplicate_choice_finish_in_event_order() -> None:
    state = ChatAttemptState()
    _observe(state, {"choices": [{"index": 0, "delta": dict[str, Any](), "finish_reason": "B"}]}, 0)
    facts = state.read(
        _frame(
            {
                "choices": [
                    {"index": 0, "delta": dict[str, Any](), "finish_reason": "A"},
                    {"index": 0, "delta": dict[str, Any](), "finish_reason": "B"},
                ]
            },
            1,
        )
    )

    before = state.held_bytes
    delta = state.additional_held_bytes(facts)
    state.observe(facts)

    assert before + delta == state.held_bytes
    assert [issue.code for issue in state.observation_facts().issues].count(
        "chat_string_field_conflict"
    ) == 1


def test_prospective_delta_replays_duplicate_tool_identity_in_event_order() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "B",
                                "function": {"name": "B"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        0,
    )
    facts = state.read(
        _frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "A",
                                    "function": {"name": "A"},
                                }
                            ]
                        },
                        "finish_reason": None,
                    },
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "B",
                                    "function": {"name": "B"},
                                }
                            ]
                        },
                        "finish_reason": None,
                    },
                ]
            },
            1,
        )
    )

    before = state.held_bytes
    delta = state.additional_held_bytes(facts)
    state.observe(facts)

    assert before + delta == state.held_bytes
    assert [issue.code for issue in state.observation_facts().issues].count(
        "chat_string_field_conflict"
    ) == 2


def test_prospective_delta_replays_duplicate_unknown_in_event_order() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {"choices": [{"index": 0, "delta": {"future": "B"}, "finish_reason": None}]},
        0,
    )
    facts = state.read(
        _frame(
            {
                "choices": [
                    {"index": 0, "delta": {"future": "A"}, "finish_reason": None},
                    {"index": 0, "delta": {"future": "B"}, "finish_reason": None},
                ]
            },
            1,
        )
    )

    before = state.held_bytes
    delta = state.additional_held_bytes(facts)
    state.observe(facts)

    assert before + delta == state.held_bytes
    assert [issue.code for issue in state.observation_facts().issues].count(
        "chat_unknown_field_conflict"
    ) == 1


def test_size_methods_do_not_materialize_and_projection_size_matches_json_response() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-size",
            "created": 1,
            "model": "模型",
            "fraction": 1e-7,
            "large": 10**100,
            "escaped": "quote=\" newline=\n tab=\t",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "答\n案"},
                    "finish_reason": "stop",
                }
            ],
        },
        0,
    )
    _observe(state, "[DONE]", 1)

    with patch.object(
        ChatAttemptState,
        "to_completion_payload",
        side_effect=AssertionError("projection materialized during sizing"),
    ):
        reservation = state.projection_reservation()
        projection_size = state.projection_size_bytes()
    with patch.object(
        ChatAttemptState,
        "observation_facts",
        side_effect=AssertionError("snapshot materialized during sizing"),
    ):
        observation_size = state.observation_size_bytes()

    payload = state.to_completion_payload()
    expected_body = JSONResponse(payload).body
    assert state.to_completion_bytes(reservation) == expected_body
    assert projection_size == len(expected_body)
    assert reservation.output_bytes == len(expected_body)
    assert reservation.working_copy_bytes == reservation.output_bytes
    assert reservation.total_bytes == reservation.output_bytes * 2
    assert observation_size >= 0


def test_large_projection_reservation_covers_both_live_logical_copies() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "id": "chatcmpl-large",
            "created": 1,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "x" * 2_000_000},
                    "finish_reason": "stop",
                }
            ],
        },
        0,
    )
    _observe(state, "[DONE]", 1)
    reservation = state.projection_reservation()
    expected = JSONResponse(state.to_completion_payload()).body

    with patch.object(
        ChatAttemptState,
        "to_completion_payload",
        side_effect=AssertionError("mapping materialized by byte writer"),
    ):
        body = state.to_completion_bytes(reservation)

    assert body == expected
    assert reservation.output_bytes == len(expected)
    assert reservation.working_copy_bytes == len(expected)
    assert reservation.total_bytes == len(expected) * 2


def test_deep_projection_reservation_scales_with_structure() -> None:
    shallow = ChatAttemptState()
    deep = ChatAttemptState()
    nested: object = "leaf"
    for _ in range(100):
        nested = [nested]
    base = {
        "id": "chatcmpl-depth",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": dict[str, Any](), "finish_reason": "stop"}],
    }
    _observe(shallow, {**base, "future": "leaf"}, 0)
    _observe(shallow, "[DONE]", 1)
    _observe(deep, {**base, "future": nested}, 0)
    _observe(deep, "[DONE]", 1)

    shallow_reservation = shallow.projection_reservation()
    deep_reservation = deep.projection_reservation()

    assert deep_reservation.output_bytes > shallow_reservation.output_bytes
    assert deep_reservation.working_copy_bytes == deep_reservation.output_bytes
    assert deep_reservation.total_bytes == deep_reservation.output_bytes * 2


def test_many_choice_observation_reservation_scales_with_record_count() -> None:
    small = ChatAttemptState()
    many = ChatAttemptState()
    _observe(
        small,
        {"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": "stop"}]},
        0,
    )
    _observe(
        many,
        {
            "choices": [
                {"index": index, "delta": {"role": "assistant"}, "finish_reason": "stop"}
                for index in range(5_000)
            ]
        },
        0,
    )
    with patch.object(
        ChatAttemptState,
        "observation_facts",
        side_effect=AssertionError("snapshot materialized during reservation"),
    ):
        small_reservation = small.observation_reservation()
        many_reservation = many.observation_reservation()

    snapshot = many.observation_facts(many_reservation)
    assert len(snapshot.choices) == 5_000
    assert (
        many_reservation.output_bytes - small_reservation.output_bytes
        > 5_000 * 20
    )
    assert many_reservation.working_copy_bytes == many_reservation.output_bytes
    assert many_reservation.total_bytes == many_reservation.output_bytes * 2


_LOGPROBS_CASES: list[tuple[list[dict[str, object]], dict[str, object]]] = [
    ([{"content": None, "refusal": None}], {"content": None, "refusal": None}),
    ([{"content": None}, {"content": list[object]()}], {"content": list[object]()}),
    (
        [{"content": [{"token": "x"}]}, {"content": None}],
        {"content": [{"token": "x"}]},
    ),
]


@pytest.mark.parametrize(
    ("logprobs_sequence", "expected"),
    _LOGPROBS_CASES,
    ids=["only-null", "null-then-empty-array", "array-then-null"],
)
def test_logprobs_fields_keep_absent_null_and_array_states(
    logprobs_sequence: list[dict[str, object]],
    expected: dict[str, object],
) -> None:
    state = ChatAttemptState()
    for ordinal, logprobs in enumerate(logprobs_sequence):
        _observe(
            state,
            {
                "id": "chatcmpl-logprobs",
                "created": 1,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "delta": dict[str, Any](),
                        "finish_reason": "stop",
                        "logprobs": logprobs,
                    }
                ],
            },
            ordinal,
        )
    _observe(state, "[DONE]", len(logprobs_sequence))

    assert state.to_completion_payload()["choices"][0]["logprobs"] == expected


def test_invalid_choice_and_tool_indices_retain_raw_facts_with_provenance() -> None:
    state = ChatAttemptState()
    invalid_choice = _frame(
        {
            "id": "chatcmpl-invalid",
            "created": 1,
            "model": "m",
            "choices": [
                {
                    "index": "bad",
                    "delta": {"content": "lost", "future_delta": {"large": "value"}},
                    "future_choice": 7,
                }
            ]
        },
        23,
        start=400,
    )
    state.observe(state.read(invalid_choice))
    invalid_tool = _frame(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": False,
                                "id": "lost-call",
                                "function": {"name": "lost-tool", "future": 1},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        24,
        start=invalid_choice.end,
    )
    state.observe(state.read(invalid_tool))
    _observe(state, "[DONE]", 25)

    snapshot = state.observation_facts()

    assert len(snapshot.unattributed) == 2
    choice_fact, tool_fact = snapshot.unattributed
    assert (choice_fact.frame_ordinal, choice_fact.start, choice_fact.end) == (
        23,
        400,
        invalid_choice.end,
    )
    assert choice_fact.field_path == "choices[0]"
    assert thaw_json(choice_fact.value.value) == {
        "index": "bad",
        "delta": {"content": "lost", "future_delta": {"large": "value"}},
        "future_choice": 7,
    }
    assert (tool_fact.frame_ordinal, tool_fact.start, tool_fact.end) == (
        24,
        invalid_choice.end,
        invalid_tool.end,
    )
    assert thaw_json(tool_fact.value.value) == {
        "index": False,
        "id": "lost-call",
        "function": {"name": "lost-tool", "future": 1},
    }
    with pytest.raises(ChatCompletionUnassemblable) as caught:
        state.to_completion_payload()
    assert caught.value.frame_ordinal == 23
    assert caught.value.start == invalid_choice.start
    assert caught.value.end == invalid_choice.end


def test_choice_and_message_unknown_fields_cannot_overwrite_each_other() -> None:
    state = ChatAttemptState()
    _observe(
        state,
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"from_choice": 1},
                    "delta": {"future_delta": 2},
                    "finish_reason": None,
                }
            ]
        },
        0,
    )

    choice = state.observation_facts().choices[0]

    assert thaw_json(choice.choice_unknown) == {"message": {"from_choice": 1}}
    assert thaw_json(choice.message_unknown) == {"future_delta": 2}
    assert any(
        issue.code == "chat_unknown_reserved_name_collision"
        for issue in state.observation_facts().issues
    )


def test_error_state_retains_reason_spellings_and_frame_end_without_reparse() -> None:
    state = ChatAttemptState()
    error_frame = _frame(
        {"error": {"code": "rate_limited", "type": "rate_limit_error"}},
        8,
        event="error",
        start=700,
    )

    state.observe(state.read(error_frame))
    snapshot = state.observation_facts()

    assert snapshot.semantic_end_offset == error_frame.end
    assert snapshot.error_values == ("rate_limited", "rate_limit_error")
    assert snapshot.error_retry_reason is not None
    assert snapshot.error_retry_reason.value == "serverError"
    assert state.semantic_end_offset == error_frame.end
    assert state.error_values == snapshot.error_values
    assert state.error_retry_reason is snapshot.error_retry_reason


def test_error_event_with_json_null_preserves_explicit_null() -> None:
    state = ChatAttemptState()
    error_frame = _frame("null", 9, event="error", start=750)

    state.observe(state.read(error_frame))
    snapshot = state.observation_facts()

    assert snapshot.stream_error.availability is JsonAvailability.EXPLICIT_NULL
    assert snapshot.semantic_end_offset == error_frame.end


def test_known_error_with_unfreezable_future_value_retains_classification() -> None:
    state = ChatAttemptState()
    error_frame = _frame(
        '{"error":{"code":"server_error"},"future":1e400}',
        9,
        event="error",
        start=800,
    )

    state.observe(state.read(error_frame))
    snapshot = state.observation_facts()

    assert snapshot.stream_error.availability is JsonAvailability.UNREADABLE
    assert snapshot.error_values == ("server_error",)
    assert snapshot.error_retry_reason is not None
    assert snapshot.semantic_end_offset == error_frame.end


def test_usage_observation_distinguishes_six_states_and_null_does_not_clear_projection() -> None:
    absent = ChatAttemptState()
    null = ChatAttemptState()
    empty = ChatAttemptState()
    zero = ChatAttemptState()
    wrong = ChatAttemptState()
    inconsistent = ChatAttemptState()
    _observe(null, {"usage": None}, 0)
    _observe(empty, {"usage": {}}, 0)
    _observe(
        zero,
        {
            "id": "c",
            "created": 1,
            "model": "m",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "choices": [{"index": 0, "delta": dict[str, Any](), "finish_reason": "stop"}],
        },
        0,
    )
    _observe(zero, {"usage": None}, 1)
    _observe(zero, "[DONE]", 2)
    _observe(wrong, {"usage": {"prompt_tokens": "many", "prompt_tokens_details": []}}, 0)
    _observe(
        inconsistent,
        {"usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 99}},
        0,
    )

    null_usage = null.observation_facts().usage
    empty_usage = empty.observation_facts().usage
    zero_usage = zero.observation_facts().usage
    wrong_usage = wrong.observation_facts().usage
    inconsistent_usage = inconsistent.observation_facts().usage
    assert absent.observation_facts().usage is None
    assert null_usage is not None
    assert null_usage.raw.availability is JsonAvailability.EXPLICIT_NULL
    assert empty_usage is not None
    assert empty_usage.raw.value is not None
    assert thaw_json(empty_usage.raw.value) == {}
    assert zero_usage is not None
    assert zero_usage.raw.availability is JsonAvailability.EXPLICIT_NULL
    assert zero.to_completion_payload()["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert wrong_usage is not None
    assert {issue.code for issue in wrong_usage.issues} == {
        "chat_usage_detail_invalid",
        "chat_usage_value_invalid",
    }
    assert inconsistent_usage is not None
    assert inconsistent_usage.issues[0].code == "usage_inconsistent"


def test_openai_sdk_agrees_on_standard_logprobs_null_positive_example() -> None:
    chunks: list[dict[str, Any]] = [
        {
            "id": "chatcmpl-sdk",
            "created": 1,
            "model": "m",
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": "{\"x\":",
                                },
                            }
                        ],
                    },
                    "finish_reason": None,
                    "logprobs": {"content": None, "refusal": None},
                }
            ],
        },
        {
            "id": "chatcmpl-sdk",
            "created": 1,
            "model": "m",
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": "x",
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": "1}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                    "logprobs": None,
                }
            ],
        },
    ]
    sdk = ChatCompletionStreamState()
    state = ChatAttemptState()
    for ordinal, chunk in enumerate(chunks):
        list(sdk.handle_chunk(ChatCompletionChunk.model_validate(chunk)))
        _observe(state, chunk, ordinal)
    _observe(state, "[DONE]", len(chunks))

    sdk_payload = sdk.get_final_completion().model_dump(exclude_unset=True)
    ours = state.to_completion_payload()
    sdk_choice = sdk_payload["choices"][0]
    ours_choice = ours["choices"][0]
    sdk_tool = sdk_choice["message"]["tool_calls"][0]
    sdk_tool.pop("index", None)
    sdk_tool["function"].pop("parsed_arguments", None)

    assert {
        "id": sdk_payload["id"],
        "object": sdk_payload["object"],
        "created": sdk_payload["created"],
        "model": sdk_payload["model"],
        "choice": {
            "index": sdk_choice["index"],
            "finish_reason": sdk_choice["finish_reason"],
            "logprobs": sdk_choice["logprobs"],
            "role": sdk_choice["message"]["role"],
            "content": sdk_choice["message"]["content"],
            "refusal": sdk_choice["message"]["refusal"],
            "tool_calls": [sdk_tool],
        },
    } == {
        "id": ours["id"],
        "object": ours["object"],
        "created": ours["created"],
        "model": ours["model"],
        "choice": {
            "index": ours_choice["index"],
            "finish_reason": ours_choice["finish_reason"],
            "logprobs": ours_choice["logprobs"],
            "role": ours_choice["message"]["role"],
            "content": ours_choice["message"]["content"],
            "refusal": ours_choice["message"]["refusal"],
            "tool_calls": ours_choice["message"]["tool_calls"],
        },
    }
    assert "parsed" not in ours_choice["message"]
    assert all("index" not in tool for tool in ours_choice["message"].get("tool_calls", []))
