from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast

import orjson
import pytest

from app.delivery import (
    AnthropicSseRenderer,
    DeliveryOrderError,
    DeliveryOutcome,
    DeliverySession,
    DeliveryWriter,
    InMemoryDeliverySink,
    RenderedBatch,
    ResponsesDeliveryError,
    SingleWriterViolation,
    TerminalUsage,
)
from app.openai.responses_stream_parser import (
    BlockIdentity,
    CompletedBlock,
    FunctionCallBlock,
    ReasoningBlock,
    ResponsesStreamParser,
    ResponsesTerminal,
    SourceOpened,
    TextBlock,
)


def _block(
    order: int,
    content: TextBlock | FunctionCallBlock | ReasoningBlock,
    *,
    completion_order: int | None = None,
) -> CompletedBlock:
    return CompletedBlock(
        identity=BlockIdentity(order, f"item_{order}", None),
        content=content,
        first_observed_order=order,
        completion_order=order if completion_order is None else completion_order,
    )


def _events(batch: bytes) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for frame in batch.split(b"\n\n"):
        if not frame:
            continue
        event_name: str | None = None
        data: bytes | None = None
        for line in frame.splitlines():
            if line.startswith(b"event: "):
                event_name = line.removeprefix(b"event: ").decode()
            elif line.startswith(b"data: "):
                data = line.removeprefix(b"data: ")
        assert event_name is not None and data is not None
        payload = orjson.loads(data)
        assert isinstance(payload, dict)
        typed_payload = cast(dict[str, Any], payload)
        assert typed_payload["type"] == event_name
        events.append((event_name, typed_payload))
    return events


def _session() -> tuple[DeliverySession, InMemoryDeliverySink]:
    sink = InMemoryDeliverySink()
    return (
        DeliverySession(
            renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
            sink=sink,
        ),
        sink,
    )


async def _consume_parser_event(
    parser: ResponsesStreamParser,
    session: DeliverySession,
    event: dict[str, Any],
    *,
    terminal_usage: TerminalUsage | None = None,
) -> tuple[RenderedBatch, ...]:
    semantic_events = parser.process(event)
    return await session.consume(
        semantic_events,
        open_identities=parser.open_blocks,
        terminal_usage=terminal_usage,
    )


@pytest.mark.asyncio
async def test_continuous_prefix_waits_for_a_before_delivering_a_then_b() -> None:
    session, sink = _session()
    block_a = _block(0, TextBlock("A"), completion_order=1)
    block_b = _block(1, TextBlock("B"), completion_order=0)

    assert await session.deliver(block_b) == ()
    assert sink.batches == ()
    assert session.pending_source_orders == (1,)

    accepted = await session.deliver(block_a)

    assert [batch.source_order for batch in accepted] == [0, 1]
    assert len(sink.batches) == 2
    assert [
        payload["delta"]["text"]
        for batch in sink.batches
        for name, payload in _events(batch)
        if name == "content_block_delta"
    ] == ["A", "B"]
    assert [entry.source_order for entry in session.frontier.committed_blocks] == [0, 1]


@pytest.mark.asyncio
async def test_first_batch_binds_message_start_to_the_complete_first_block() -> None:
    session, sink = _session()

    (rendered,) = await session.deliver(_block(0, TextBlock("complete")))

    names = [name for name, _ in _events(sink.batches[0])]
    assert names == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
    ]
    assert rendered.includes_message_start is True
    assert session.frontier.message_start_accepted is True
    assert len(session.frontier.committed_blocks) == 1


@pytest.mark.asyncio
async def test_thinking_block_materializes_summary_then_project_signature() -> None:
    session, sink = _session()

    await session.deliver(_block(0, ReasoningBlock("visible", "opaque-😀")))

    deltas = [
        payload["delta"]
        for name, payload in _events(sink.batches[0])
        if name == "content_block_delta"
    ]
    assert deltas == [
        {"type": "thinking_delta", "thinking": "visible"},
        {
            "type": "signature_delta",
            "signature": (
                "ghc-api-proxy:synthetic-reasoning:v1:"
                "eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIs"
                "ImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAifQ"
            ),
        },
    ]


@pytest.mark.asyncio
async def test_tool_use_batch_contains_complete_json_input() -> None:
    session, sink = _session()

    await session.deliver(
        _block(0, FunctionCallBlock("call_1", "weather", '{"city":"Paris"}'))
    )

    events = _events(sink.batches[0])
    start = next(payload for name, payload in events if name == "content_block_start")
    delta = next(payload for name, payload in events if name == "content_block_delta")
    assert start["content_block"] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "weather",
        "input": {},
    }
    assert delta["delta"] == {
        "type": "input_json_delta",
        "partial_json": '{"city":"Paris"}',
    }
    assert cast(Mapping[str, object], orjson.loads(delta["delta"]["partial_json"])) == {
        "city": "Paris"
    }


@pytest.mark.asyncio
async def test_terminal_batch_records_usage_after_all_blocks() -> None:
    session, sink = _session()
    await session.deliver(_block(0, TextBlock("done")))

    terminal = await session.finish(
        stop_reason="end_turn",
        usage=TerminalUsage(input_tokens=7, output_tokens=3),
    )

    assert terminal.kind == "terminal"
    assert [name for name, _ in _events(sink.batches[-1])] == [
        "message_delta",
        "message_stop",
    ]
    message_delta = _events(sink.batches[-1])[0][1]
    assert message_delta["delta"] == {"stop_reason": "end_turn", "stop_sequence": None}
    assert message_delta["usage"] == {
        "input_tokens": 7,
        "output_tokens": 3,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    assert session.frontier.terminal_accepted is True

    with pytest.raises(DeliveryOrderError, match="already accepted"):
        await session.finish(
            stop_reason="end_turn",
            usage=TerminalUsage(input_tokens=7, output_tokens=3),
        )
    assert len(sink.batches) == 2


def test_in_memory_sink_grants_exactly_one_writer() -> None:
    sink = InMemoryDeliverySink()

    sink.open_writer()

    with pytest.raises(SingleWriterViolation, match="already has a writer"):
        sink.open_writer()


@pytest.mark.asyncio
async def test_parser_delivery_orders_multiple_parts_within_one_item() -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()
    item = {"id": "msg_multi", "type": "message"}

    await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.added", "output_index": 0, "item": item},
    )
    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_multi",
            "content_index": 1,
            "text": "B",
        },
    )
    assert sink.batches == ()
    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_multi",
            "content_index": 0,
            "text": "A",
        },
    )
    assert sink.batches == ()

    accepted = await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 0, "item": item},
    )

    assert len(accepted) == 2
    assert [entry.identity.content_index for entry in session.frontier.committed_blocks] == [
        0,
        1,
    ]
    assert [
        payload["delta"]["text"]
        for batch in sink.batches
        for name, payload in _events(batch)
        if name == "content_block_delta"
    ] == ["A", "B"]


@pytest.mark.asyncio
async def test_parser_delivery_waits_when_later_item_completes_first() -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()
    first = {"id": "msg_first", "type": "message"}
    later = {"id": "msg_later", "type": "message"}
    for output_index, item in enumerate((first, later)):
        await _consume_parser_event(
            parser,
            session,
            {
                "type": "response.output_item.added",
                "output_index": output_index,
                "item": item,
            },
        )

    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 1,
            "item_id": "msg_later",
            "content_index": 0,
            "text": "later",
        },
    )
    await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 1, "item": later},
    )
    assert sink.batches == ()

    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_first",
            "content_index": 0,
            "text": "first",
        },
    )
    accepted = await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 0, "item": first},
    )

    assert len(accepted) == 2
    assert [entry.source_order for entry in session.frontier.committed_blocks] == [0, 1]
    assert [
        payload["delta"]["text"]
        for batch in sink.batches
        for name, payload in _events(batch)
        if name == "content_block_delta"
    ] == ["first", "later"]


@pytest.mark.asyncio
async def test_zero_block_source_does_not_leave_a_delivery_gap() -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()
    empty = {"id": "msg_empty", "type": "message"}
    text = {"id": "msg_text", "type": "message"}
    for output_index, item in enumerate((empty, text)):
        await _consume_parser_event(
            parser,
            session,
            {
                "type": "response.output_item.added",
                "output_index": output_index,
                "item": item,
            },
        )
    await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 0, "item": empty},
    )
    assert sink.batches == ()

    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 1,
            "item_id": "msg_text",
            "content_index": 7,
            "text": "after-empty",
        },
    )
    (accepted,) = await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 1, "item": text},
    )

    assert accepted.block_index == 0
    assert session.pending_source_orders == ()
    assert [entry.source_order for entry in session.frontier.committed_blocks] == [1]
    assert [
        payload["delta"]["text"]
        for name, payload in _events(sink.batches[0])
        if name == "content_block_delta"
    ] == ["after-empty"]


@pytest.mark.asyncio
async def test_typed_session_cannot_finish_before_parser_terminal() -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()
    item = {"id": "msg_complete", "type": "message"}
    await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.added", "output_index": 0, "item": item},
    )
    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_complete",
            "content_index": 0,
            "text": "complete",
        },
    )
    await _consume_parser_event(
        parser,
        session,
        {"type": "response.output_item.done", "output_index": 0, "item": item},
    )

    with pytest.raises(DeliveryOrderError, match="cannot be mixed"):
        await session.finish(
            stop_reason="end_turn",
            usage=TerminalUsage(input_tokens=1, output_tokens=1),
        )

    assert session.frontier.terminal_accepted is False
    assert len(sink.batches) == 1


@pytest.mark.asyncio
async def test_parser_incomplete_terminal_never_emits_success_terminal() -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()
    await _consume_parser_event(
        parser,
        session,
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "msg_open", "type": "message"},
        },
    )

    with pytest.raises(ResponsesDeliveryError) as caught:
        await _consume_parser_event(
            parser,
            session,
            {
                "type": "response.completed",
                "response": {"id": "resp_incomplete", "status": "completed"},
            },
            terminal_usage=TerminalUsage(input_tokens=1, output_tokens=0),
        )

    assert caught.value.kind == "incomplete"
    assert caught.value.code == "incomplete_lifecycle"
    assert caught.value.open_blocks == (BlockIdentity(0, "msg_open", None),)
    assert session.frontier.terminal_accepted is False
    assert sink.batches == ()
    with pytest.raises(ResponsesDeliveryError) as repeated:
        await session.finish(
            stop_reason="end_turn",
            usage=TerminalUsage(input_tokens=1, output_tokens=0),
        )
    assert repeated.value is caught.value
    assert sink.batches == ()


@pytest.mark.parametrize(
    ("terminal_event", "expected_kind", "expected_code"),
    [
        (
            {
                "type": "response.incomplete",
                "response": {"id": "resp_incomplete", "status": "incomplete"},
            },
            "incomplete",
            None,
        ),
        (
            {
                "type": "response.failed",
                "response": {
                    "id": "resp_failed",
                    "status": "failed",
                    "error": {"code": "server_error", "message": "failed"},
                },
            },
            "failed",
            "server_error",
        ),
        (
            {"type": "error", "code": "overloaded", "message": "try later"},
            "error",
            "overloaded",
        ),
    ],
)
@pytest.mark.asyncio
async def test_unsuccessful_terminal_kinds_poison_success_finish(
    terminal_event: dict[str, Any], expected_kind: str, expected_code: str | None
) -> None:
    parser = ResponsesStreamParser()
    session, sink = _session()

    with pytest.raises(ResponsesDeliveryError) as caught:
        await _consume_parser_event(
            parser,
            session,
            terminal_event,
            terminal_usage=TerminalUsage(input_tokens=1, output_tokens=0),
        )

    assert caught.value.kind == expected_kind
    assert caught.value.code == expected_code
    with pytest.raises(ResponsesDeliveryError) as repeated:
        await session.finish(
            stop_reason="end_turn",
            usage=TerminalUsage(input_tokens=1, output_tokens=0),
        )
    assert repeated.value is caught.value
    assert session.frontier.terminal_accepted is False
    assert sink.batches == ()


class _PausedWriter:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.batches: list[bytes] = []
        self.active_writes = 0
        self.maximum_active_writes = 0

    async def write(self, batch: bytes) -> None:
        self.active_writes += 1
        self.maximum_active_writes = max(self.maximum_active_writes, self.active_writes)
        self.entered.set()
        await self.release.wait()
        self.batches.append(batch)
        self.active_writes -= 1


class _PendingWriter:
    def __init__(self) -> None:
        self.batches: list[bytes] = []

    async def write(self, batch: bytes) -> DeliveryOutcome:
        self.batches.append(batch)
        return "pending"


class _PendingSink:
    def __init__(self, writer: _PendingWriter) -> None:
        self._writer = writer

    def open_writer(self) -> DeliveryWriter:
        return self._writer


@pytest.mark.asyncio
async def test_pending_sink_write_does_not_advance_frontier_until_acknowledged() -> None:
    writer = _PendingWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
    )

    (batch,) = await session.deliver(_block(0, TextBlock("pending")))

    assert len(writer.batches) == 1
    assert session.frontier.headers_state == "not_started"
    assert session.frontier.message_start_state == "not_started"
    assert session.frontier.committed_blocks == ()

    await session.acknowledge_data(batch.data, "accepted")

    assert session.frontier.headers_state == "accepted"
    assert session.frontier.message_start_state == "accepted"
    assert [entry.block.content for entry in session.frontier.committed_blocks] == [
        TextBlock("pending")
    ]


@pytest.mark.asyncio
async def test_uncertain_sink_write_never_becomes_committed() -> None:
    writer = _PendingWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
    )
    (batch,) = await session.deliver(_block(0, TextBlock("uncertain")))

    session.frontier.accept_headers()
    await session.acknowledge_data(batch.data, "uncertain")

    assert session.frontier.delivery_uncertain is True
    assert session.frontier.headers_state == "accepted"
    assert session.frontier.message_start_state == "uncertain"
    assert session.frontier.block_state(0) == "uncertain"
    assert session.frontier.committed_blocks == ()


@pytest.mark.asyncio
async def test_max_output_tokens_incomplete_finishes_with_max_tokens() -> None:
    session, sink = _session()
    terminal = ResponsesTerminal(
        "incomplete",
        "resp_limited",
        "incomplete",
        "max_output_tokens",
        None,
        (),
    )

    await session.consume(
        (terminal,),
        open_identities=(),
        terminal_usage=TerminalUsage(input_tokens=3, output_tokens=5),
        stop_reason="max_tokens",
    )

    names = [name for name, _ in _events(sink.batches[0])]
    assert names == ["message_start", "message_delta", "message_stop"]
    assert _events(sink.batches[0])[1][1]["delta"]["stop_reason"] == "max_tokens"
    assert session.frontier.terminal_accepted is True


class _PausedSink:
    def __init__(self, writer: _PausedWriter) -> None:
        self._writer = writer

    def open_writer(self) -> DeliveryWriter:
        return self._writer


@pytest.mark.asyncio
async def test_concurrent_consume_serializes_block_and_terminal_writes() -> None:
    writer = _PausedWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PausedSink(writer),
    )
    block = CompletedBlock(
        identity=BlockIdentity(0, "msg_0", 0),
        content=TextBlock("first"),
        first_observed_order=0,
        completion_order=0,
    )
    block_task = asyncio.create_task(
        session.consume(
            (SourceOpened(BlockIdentity(0, "msg_0", None), 0), block),
            open_identities=(),
        )
    )
    await writer.entered.wait()
    terminal_task = asyncio.create_task(
        session.consume(
            (ResponsesTerminal("completed", "resp_0", "completed", None, None, ()),),
            open_identities=(),
            terminal_usage=TerminalUsage(input_tokens=1, output_tokens=1),
        )
    )
    await asyncio.sleep(0)

    assert writer.active_writes == 1
    assert writer.maximum_active_writes == 1
    assert terminal_task.done() is False

    writer.release.set()
    await asyncio.gather(block_task, terminal_task)

    assert writer.maximum_active_writes == 1
    assert [name for batch in writer.batches for name, _ in _events(batch)] == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


@pytest.mark.asyncio
async def test_concurrent_deliver_and_finish_cannot_overtake_one_writer() -> None:
    writer = _PausedWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PausedSink(writer),
    )
    deliver_task = asyncio.create_task(session.deliver(_block(0, TextBlock("first"))))
    await writer.entered.wait()
    finish_task = asyncio.create_task(
        session.finish(
            stop_reason="end_turn",
            usage=TerminalUsage(input_tokens=1, output_tokens=1),
        )
    )
    await asyncio.sleep(0)

    assert writer.active_writes == 1
    assert writer.maximum_active_writes == 1
    assert finish_task.done() is False

    writer.release.set()
    await asyncio.gather(deliver_task, finish_task)

    assert writer.maximum_active_writes == 1
    assert [name for batch in writer.batches for name, _ in _events(batch)] == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]