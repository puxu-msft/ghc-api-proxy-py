"""The Responses framer is checked against the client library that has to read it.

Asserting our own bytes would only prove the framer agrees with whatever this file expects. What decides whether a stream is well-formed is the OpenAI SDK's own parser: it raises when `response.created` is missing, asserts on the snapshot's shape before applying a text delta, indexes `snapshot.output[output_index]` directly, and refuses a stream that never says it completed. So the frames go through `ResponseStreamState` and the assertions are made on the response it reconstructs.

`tests/int/cassettes/anthropic_to_responses_stream.json` is where the wire envelope and the event payload shapes were read from; this file does not replay it, because what is under test is the direction that has no recording — ours, going out.
"""

from typing import Any, cast, get_args

import orjson
import pytest
from openai._models import construct_type
from openai._types import omit
from openai.lib.streaming.responses import ResponseStreamState
from openai.types.responses import ParsedResponse
from openai.types.responses.response_stream_event import ResponseStreamEvent

from app.errors import ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.blocks import TEXT, THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.formats.openai_responses import ResponsesFramer


def framer() -> ResponsesFramer:
    return ResponsesFramer(response_id="resp_test", model="gpt-5.5", created_at=1_700_000_000)


def events_of(frames: tuple[bytes, ...]) -> list[str]:
    """The event names on the wire, in order, read off the `event:` line rather than the payload."""
    names: list[str] = []
    for frame in frames:
        head = frame.decode().split("\n", 1)[0]
        if head.startswith("event: "):
            names.append(head.removeprefix("event: "))
    return names


def as_event(frame: bytes) -> Any:
    """One frame decoded back into the SDK's own event object.

    `construct_type` is the SDK's loose constructor and it answers `object`, so the cast is here once rather than at each call site. It is the same path the SDK's SSE decoder takes, which is the point — the events the parser sees under test are built the way it builds them.
    """
    payload = orjson.loads(frame.decode().split("data: ", 1)[1])
    return cast(Any, construct_type(value=payload, type_=ResponseStreamEvent))


def replay(frames: list[bytes]) -> ParsedResponse[Any]:
    """Feed the frames to the SDK's parser and return the response it reconstructs.

    Comments are skipped the way any SSE reader skips them — that is the assertion the keep-alive test makes, and it has to be made through this path rather than beside it.
    """
    state: ResponseStreamState[Any] = ResponseStreamState(input_tools=[], text_format=omit)
    for frame in frames:
        if frame.decode().startswith(":"):
            continue
        state.handle_event(as_event(frame))
    completed = state._completed_response  # pyright: ignore[reportPrivateUsage]
    assert completed is not None, "the stream never said it completed"
    return completed


def text_block(index: int, text: str) -> CompletedBlock:
    return CompletedBlock(index=index, kind=TEXT, payload={"type": TEXT, TEXT: text})


def whole(framer_: ResponsesFramer, blocks: list[CompletedBlock], terminal: Terminal) -> list[bytes]:
    frames = list(framer_.preamble())
    for block in blocks:
        frames.extend(framer_.block(block))
    frames.extend(framer_.terminal(terminal))
    return frames


def test_the_sdk_reconstructs_the_text_it_was_sent() -> None:
    response = replay(
        whole(
            framer(),
            [text_block(0, "Hello"), text_block(1, " world")],
            Terminal(stop_reason="end_turn", seen=True, upstream_usage={"input_tokens": 7}),
        )
    )

    assert response.status == "completed"
    assert response.model == "gpt-5.5"
    assert [item.type for item in response.output] == ["message", "message"]
    assert response.output_text == "Hello world"
    assert response.usage is not None
    assert response.usage.input_tokens == 7


def test_output_index_is_renumbered_rather_than_taken_from_the_block() -> None:
    """The assembler's counter skips numbers, and the SDK's snapshot list cannot.

    `CompletedBlock.index` advances for items the assembler later drops, so a delivered stream can carry blocks numbered 0 and 2. The SDK appends to `snapshot.output` and then indexes it by `output_index`; a gap is an IndexError, one frame after the block that skipped.
    """
    response = replay(
        whole(
            framer(),
            [text_block(0, "first"), text_block(7, "second")],
            Terminal(stop_reason="end_turn", seen=True),
        )
    )

    assert len(response.output) == 2
    assert response.output_text == "firstsecond"


def test_a_tool_call_keeps_upstreams_call_id_and_its_arguments() -> None:
    block = CompletedBlock(
        index=0,
        kind=TOOL_USE,
        payload={"type": TOOL_USE, "id": "call_abc", "name": "get_weather", "input": {"city": "SF"}},
    )
    response = replay(
        whole(framer(), [block], Terminal(stop_reason="tool_use", seen=True))
    )

    # The item types are a union; which member this is, is the assertion below.
    call = cast(Any, response.output[0])
    assert call.type == "function_call"
    assert call.call_id == "call_abc"
    assert call.name == "get_weather"
    assert orjson.loads(call.arguments) == {"city": "SF"}
    # `tool_use` is this proxy's word for a finished turn, not one Responses has.
    assert response.status == "completed"


def test_unparsable_tool_arguments_are_handed_back_as_they_arrived() -> None:
    """The assembler wraps arguments it could not parse. The wrapper must not reach the client."""
    block = CompletedBlock(
        index=0,
        kind=TOOL_USE,
        payload={
            "type": TOOL_USE,
            "id": "call_x",
            "name": "f",
            "input": {"__raw": '{"city": "SF'},
        },
    )
    frames = whole(framer(), [block], Terminal(stop_reason="tool_use", seen=True))
    response = replay(frames)

    assert cast(Any, response.output[0]).arguments == '{"city": "SF'


def test_reasoning_carries_encrypted_content_only_when_there_was_some() -> None:
    """An empty carrier is still a non-empty marker string, and emitting it would be a fabricated token."""
    from app.pipeline.translation_driver.reasoning_carrier import encode_reasoning_carrier

    with_content = CompletedBlock(
        index=0,
        kind=THINKING,
        payload={
            "type": THINKING,
            THINKING: "thought about it",
            "signature": encode_reasoning_carrier("sealed-bytes"),
        },
    )
    without = CompletedBlock(
        index=1,
        kind=THINKING,
        payload={"type": THINKING, THINKING: "", "signature": encode_reasoning_carrier(None)},
    )
    response = replay(
        whole(framer(), [with_content, without], Terminal(stop_reason="end_turn", seen=True))
    )

    first, second = cast(Any, response.output[0]), cast(Any, response.output[1])
    assert first.type == "reasoning"
    assert [part.text for part in first.summary] == ["thought about it"]
    assert first.encrypted_content == "sealed-bytes"
    assert second.summary == []
    assert second.encrypted_content is None


def test_a_truncated_turn_completes_as_incomplete_with_upstreams_reason() -> None:
    """Truncation ends the stream with `response.incomplete`, which is not a success and is not framed as one.

    The SDK only ever fills its final response from `response.completed`, so a caller that asks for one here gets nothing — exactly what it gets from real upstream, which ends a truncated turn the same way. What a caller can read is the event itself, so that is what is asserted.
    """
    frames = whole(
        framer(),
        [text_block(0, "half a sen")],
        Terminal(stop_reason="max_tokens", seen=True, upstream_usage={"output_tokens": 64}),
    )
    state: ResponseStreamState[Any] = ResponseStreamState(input_tools=[], text_format=omit)
    for frame in frames:
        state.handle_event(as_event(frame))

    assert events_of(tuple(frames))[-1] == "response.incomplete"
    last = orjson.loads(frames[-1].decode().split("data: ", 1)[1])["response"]
    assert last["status"] == "incomplete"
    assert last["incomplete_details"] == {"reason": "max_output_tokens"}
    assert last["usage"] == {"output_tokens": 64}
    # The text that did arrive is still in the output, because half an answer beats none.
    assert last["output"][0]["content"][0]["text"] == "half a sen"


def test_usage_is_absent_rather_than_zero_when_upstream_never_sent_it() -> None:
    """A usage of zero is a measurement. Not having one is not."""
    response = replay(
        whole(framer(), [text_block(0, "hi")], Terminal(stop_reason="end_turn", seen=True))
    )

    assert response.usage is None


def test_the_preamble_is_the_first_thing_and_names_the_response() -> None:
    """`response.created` first is the SDK's one hard requirement; everything else it tolerates."""
    frames = whole(framer(), [text_block(0, "hi")], Terminal(stop_reason="end_turn", seen=True))

    assert events_of(tuple(frames))[:2] == ["response.created", "response.in_progress"]
    assert events_of(tuple(frames))[-1] == "response.completed"


def test_sequence_numbers_never_repeat_and_never_go_backwards() -> None:
    frames = whole(
        framer(),
        [text_block(0, "a"), text_block(1, "b")],
        Terminal(stop_reason="end_turn", seen=True),
    )
    numbers = [
        orjson.loads(frame.decode().split("data: ", 1)[1])["sequence_number"] for frame in frames
    ]

    assert numbers == list(range(len(numbers)))


def test_every_event_carries_the_fields_its_model_declares_required() -> None:
    """The layer `ResponseStreamState` cannot see.

    The SDK decodes events with `construct_type`, which coerces loosely and never validates, so a frame missing a required field parses fine, reconstructs fine, and passes every other test in this file.
    It found `response.function_call_arguments.done` shipping without `name` and the two `output_text` events without `logprobs` — invisible to every other oracle here, and a rejection in any client that validates its input.

    Read off the SDK's own models rather than a list written here, so a field the library adds later shows up as a failure instead of as nothing.
    """
    one = framer()
    frames = list(one.preamble())
    frames.extend(one.block(text_block(0, "hi")))
    frames.extend(
        one.block(
            CompletedBlock(
                index=1,
                kind=TOOL_USE,
                payload={"type": TOOL_USE, "id": "c", "name": "f", "input": {}},
            )
        )
    )
    frames.extend(
        one.block(
            CompletedBlock(
                index=2, kind=THINKING, payload={"type": THINKING, THINKING: "t", "signature": ""}
            )
        )
    )
    frames.extend(one.terminal(Terminal(stop_reason="end_turn", seen=True)))
    frames.append(one.error(ErrorInfo(category=ErrorCategory.UPSTREAM, message="boom", status_code=502, code="c")))

    # `ResponseStreamEvent` is an annotated union; its members carry `type` as a Literal rather than as a default, so the discriminator is read out of the annotation.
    members = get_args(get_args(ResponseStreamEvent)[0])
    by_type: dict[str, Any] = {}
    for member in members:
        literal = get_args(member.model_fields["type"].annotation)
        if literal:
            by_type[literal[0]] = member
    missing: dict[str, list[str]] = {}
    for frame in frames:
        payload = orjson.loads(frame.decode().split("data: ", 1)[1])
        model = by_type.get(payload["type"])
        assert model is not None, f"no SDK model declares type {payload['type']!r}"
        absent = [
            name
            for name, field in model.model_fields.items()
            if field.is_required() and name not in payload
        ]
        if absent:
            missing[payload["type"]] = absent

    assert missing == {}


def test_the_keepalive_is_a_comment_no_parser_turns_into_an_event() -> None:
    one = framer()
    frames = list(one.preamble())
    frames.append(one.keepalive())
    frames.extend(one.block(text_block(0, "hi")))
    frames.extend(one.terminal(Terminal(stop_reason="end_turn", seen=True)))

    response = replay(frames)
    assert response.output_text == "hi"

    # And it consumed no sequence number, which the comment used to claim while asserting only the bytes. Read off the wire rather than off the framer: the numbers a client sees are the claim.
    numbers = [
        orjson.loads(f.decode().split("data: ", 1)[1])["sequence_number"]
        for f in frames
        if not f.startswith(b":")
    ]
    assert numbers == list(range(len(numbers)))


def test_an_error_frame_says_what_went_wrong_without_claiming_a_response() -> None:
    """`response.failed` would have to carry a whole `Response`, and mid-stream there is not one to give."""
    one = framer()
    frames = list(one.preamble())
    frames.extend(one.block(text_block(0, "partial")))
    frames.append(
        one.error(
            ErrorInfo(
                category=ErrorCategory.UPSTREAM,
                message="Responses stream ended before a successful terminal event",
                status_code=502,
                code="incomplete_responses_stream",
            )
        )
    )

    assert events_of(tuple(frames))[-1] == "error"
    payload = orjson.loads(frames[-1].decode().split("data: ", 1)[1])
    assert payload["code"] == "incomplete_responses_stream"
    # This leg spells the category itself now; the caller names it and nothing else. `server_error` is what `UPSTREAM` reads as here — an assertion on the prefix would have passed whatever the leg chose.
    assert payload["message"].startswith("server_error: ")
    # Flat, and that is the contract: `ResponseErrorEvent` has no nested `error` object, so the Anthropic leg's shape must not leak across.
    assert "error" not in payload
    assert payload["param"] is None

    # The stream stopped without completing, which is exactly what the client must not be able to read as success.
    with pytest.raises(AssertionError):
        replay(frames)


def test_a_block_kind_this_does_not_know_is_refused_rather_than_emptied() -> None:
    """An unrecognised kind used to become an empty message item.

    `_message` reads `payload[TEXT]`, which an unknown kind has no key for, so the client was handed an empty assistant turn — and "we did not recognise this" was delivered as "upstream produced nothing". It can only happen if a block kind is added without this switch, so it fails where that mistake is, the same way `block_frames` refuses a compat mode it does not implement.
    """
    one = framer()
    with pytest.raises(ValueError, match="no Responses item shape"):
        one.block(CompletedBlock(index=0, kind="server_tool_use", payload={"type": "x"}))


@pytest.mark.parametrize(
    ("stop_reason", "expected"),
    [
        ("max_tokens", "max_output_tokens"),
        # Written by the assembler when upstream said incomplete and gave no reason.
        ("incomplete", None),
        # Anthropic's vocabulary. Reachable only through a route this proxy cannot build today, but the passthrough that used to send them had no way of knowing that.
        ("stop_sequence", None),
        ("refusal", None),
    ],
)
def test_only_reasons_the_protocol_has_a_word_for_reach_incomplete_details(
    stop_reason: str, expected: str | None
) -> None:
    """`incomplete_details.reason` is an enumeration, so an unmapped reason is a null, not our word."""
    one = framer()
    one.preamble()
    one.block(text_block(0, "partial"))
    frames = one.terminal(Terminal(stop_reason=stop_reason, seen=True))

    payload = orjson.loads(frames[-1].decode().split("data: ", 1)[1])["response"]
    assert payload["status"] == "incomplete"
    assert payload["incomplete_details"] == ({"reason": expected} if expected else None)
