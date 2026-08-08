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
from app.delivery.reservation import (
    RequestResidentAccount,
    ResidentByteBudget,
    ResidentCapacityError,
    ResidentLease,
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
    def __init__(self, writer: DeliveryWriter) -> None:
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


class _DiscardingWriter:
    def __init__(self) -> None:
        self.write_count = 0

    async def write(self, batch: bytes) -> DeliveryOutcome:
        self.write_count += 1
        return "accepted"


class _DiscardingSink:
    def __init__(self) -> None:
        self.writer = _DiscardingWriter()

    def open_writer(self) -> DeliveryWriter:
        return self.writer


@pytest.mark.asyncio
async def test_opt_in_resident_account_tracks_delivery_payload_until_close() -> None:
    budget = ResidentByteBudget(capacity_bytes=4096)
    account = RequestResidentAccount(
        request_id="request-happy",
        attempt=1,
        capacity_bytes=4096,
        budget=budget,
    )
    writer = _PendingWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
        resident_account=account,
    )
    semantic_bytes = len("resident-😀".encode())

    (batch,) = await session.deliver(_block(0, TextBlock("resident-😀")))

    assert batch.kind == "block"
    assert writer.batches == [batch.data]
    assert account.high_water_bytes == semantic_bytes + len(batch.data)
    assert budget.high_water_bytes == semantic_bytes + len(batch.data)
    assert account.current_bytes == semantic_bytes + len(batch.data)
    assert budget.current_bytes == semantic_bytes + len(batch.data)
    assert session.frontier.committed_blocks == ()

    await session.acknowledge_data(batch.data, "accepted")

    assert account.current_bytes == semantic_bytes
    assert budget.current_bytes == semantic_bytes
    assert len(session.frontier.committed_blocks) == 1

    await session.aclose()
    await session.aclose()

    assert account.current_bytes == 0
    assert budget.current_bytes == 0
    assert account.high_water_bytes > 0


@pytest.mark.asyncio
async def test_cancelled_delivery_reservation_wait_does_not_charge_or_mutate() -> None:
    capacity_bytes = 1024
    budget = ResidentByteBudget(capacity_bytes=capacity_bytes)
    holder_account = RequestResidentAccount(
        request_id="request-holder",
        attempt=1,
        capacity_bytes=capacity_bytes,
        budget=budget,
    )
    waiting_account = RequestResidentAccount(
        request_id="request-waiting",
        attempt=1,
        capacity_bytes=capacity_bytes,
        budget=budget,
    )
    holder = await holder_account.reserve(owner="holder", amount=capacity_bytes)
    sink = _DiscardingSink()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=sink,
        resident_account=waiting_account,
    )

    delivery = asyncio.create_task(session.deliver(_block(0, TextBlock("wait"))))
    await asyncio.sleep(0)

    assert delivery.done() is False
    assert waiting_account.current_bytes == 0
    assert budget.current_bytes == capacity_bytes
    assert session.pending_source_orders == ()
    assert session.frontier.committed_blocks == ()
    assert sink.writer.write_count == 0

    delivery.cancel()
    with pytest.raises(asyncio.CancelledError):
        await delivery

    assert waiting_account.current_bytes == 0
    assert budget.current_bytes == capacity_bytes
    assert session.pending_source_orders == ()
    assert session.frontier.committed_blocks == ()
    assert sink.writer.write_count == 0

    await holder_account.release(holder)
    assert budget.current_bytes == 0
    with pytest.raises(RuntimeError, match="already released"):
        await holder_account.release(holder)
    await session.aclose()


@pytest.mark.asyncio
async def test_request_aggregate_capacity_fails_without_changing_balances() -> None:
    budget = ResidentByteBudget(capacity_bytes=20)
    account = RequestResidentAccount(
        request_id="request-aggregate",
        attempt=1,
        capacity_bytes=10,
        budget=budget,
    )
    held = await account.reserve(owner="held", amount=6)

    with pytest.raises(ResidentCapacityError) as caught:
        await account.reserve(owner="over-request-capacity", amount=5)

    assert caught.value.scope == "request"
    assert caught.value.amount == 11
    assert account.current_bytes == 6
    assert budget.current_bytes == 6
    await account.release(held)
    assert account.current_bytes == 0
    assert budget.current_bytes == 0


@pytest.mark.asyncio
async def test_reserve_many_is_all_or_nothing() -> None:
    budget = ResidentByteBudget(capacity_bytes=20)
    account = RequestResidentAccount(
        request_id="request-atomic-batch",
        attempt=1,
        capacity_bytes=10,
        budget=budget,
    )

    with pytest.raises(ResidentCapacityError) as caught:
        await account.reserve_many((("first", 6), ("second", 5)))

    assert caught.value.scope == "request"
    assert account.current_bytes == 0
    assert budget.current_bytes == 0
    first = await account.reserve(owner="first", amount=6)
    await account.release(first)


@pytest.mark.asyncio
async def test_waiting_reservation_continues_after_capacity_is_released() -> None:
    budget = ResidentByteBudget(capacity_bytes=10)
    holder_account = RequestResidentAccount(
        request_id="request-capacity-holder",
        attempt=1,
        capacity_bytes=10,
        budget=budget,
    )
    waiting_account = RequestResidentAccount(
        request_id="request-capacity-waiter",
        attempt=1,
        capacity_bytes=10,
        budget=budget,
    )
    holder = await holder_account.reserve(owner="holder", amount=8)
    waiting = asyncio.create_task(
        waiting_account.reserve(owner="waiting", amount=4)
    )
    await asyncio.sleep(0)

    assert waiting.done() is False
    assert waiting_account.current_bytes == 0
    assert budget.current_bytes == 8

    await holder_account.release(holder)
    waiting_lease = await asyncio.wait_for(waiting, timeout=1)

    assert waiting_account.current_bytes == 4
    assert budget.current_bytes == 4
    await waiting_account.release(waiting_lease)
    assert waiting_account.current_bytes == 0
    assert budget.current_bytes == 0


@pytest.mark.asyncio
async def test_resident_lease_state_and_charge_facts_are_read_only() -> None:
    budget = ResidentByteBudget(capacity_bytes=10)
    account = RequestResidentAccount(
        request_id="request-read-only-lease",
        attempt=1,
        capacity_bytes=10,
        budget=budget,
    )
    lease = await account.reserve(owner="payload", amount=5)

    for name, value in (
        ("owner", "forged"),
        ("amount", 1),
        ("_account", object()),
        ("_owner", "forged"),
        ("_amount", 1),
        ("_released", True),
    ):
        with pytest.raises(AttributeError):
            setattr(lease, name, value)
    assert not hasattr(lease, "mark_released")
    assert not hasattr(lease, "release")
    assert lease.owner == "payload"
    assert lease.amount == 5
    assert lease.released is False

    with pytest.raises(RuntimeError, match="already initialized"):
        lease.__init__("payload", 1)
    assert lease.amount == 5
    assert account.current_bytes == 5
    assert budget.current_bytes == 5

    await account.release(lease)

    assert lease.released is True
    assert account.current_bytes == 0
    assert budget.current_bytes == 0


class _OutcomeWriter:
    def __init__(self, outcome: DeliveryOutcome) -> None:
        self._outcome: DeliveryOutcome = outcome
        self.batches: list[bytes] = []

    async def write(self, batch: bytes) -> DeliveryOutcome:
        self.batches.append(batch)
        return self._outcome


@pytest.mark.asyncio
async def test_closed_session_rejects_every_write_entry_before_reserve_or_sink() -> None:
    async def assert_rejected(action: str) -> None:
        budget = ResidentByteBudget(capacity_bytes=4096)
        account = RequestResidentAccount(
            request_id=f"request-closed-{action}",
            attempt=1,
            capacity_bytes=4096,
            budget=budget,
        )
        writer = _OutcomeWriter("accepted")
        session = DeliverySession(
            renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
            sink=_PendingSink(writer),
            resident_account=account,
        )
        await session.aclose()

        with pytest.raises(DeliveryOrderError, match="closed"):
            if action == "deliver":
                await session.deliver(_block(0, TextBlock("closed")))
            elif action == "consume":
                await session.consume(
                    (
                        SourceOpened(BlockIdentity(0, "item_0", None), 0),
                        _block(0, TextBlock("closed")),
                    ),
                    open_identities=(),
                )
            elif action == "finish":
                await session.finish(
                    stop_reason="end_turn",
                    usage=TerminalUsage(input_tokens=1, output_tokens=1),
                )
            else:
                await session.render_error(
                    error_type="api_error",
                    message="closed",
                    code="closed",
                )

        assert writer.batches == []
        assert account.current_bytes == 0
        assert budget.current_bytes == 0
        await session.aclose()

    for action in ("deliver", "consume", "finish", "render_error"):
        await assert_rejected(action)


@pytest.mark.asyncio
async def test_closed_session_cannot_create_a_pending_rendered_lease() -> None:
    budget = ResidentByteBudget(capacity_bytes=4096)
    account = RequestResidentAccount(
        request_id="request-closed-pending-error",
        attempt=1,
        capacity_bytes=4096,
        budget=budget,
    )
    writer = _OutcomeWriter("pending")
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
        resident_account=account,
    )
    await session.aclose()

    with pytest.raises(DeliveryOrderError, match="closed"):
        await session.render_error(
            error_type="api_error",
            message="closed",
            code="closed",
        )

    assert writer.batches == []
    assert account.current_bytes == 0
    assert budget.current_bytes == 0


class _PausedReleaseAccount(RequestResidentAccount):
    def __init__(
        self,
        *,
        request_id: str,
        capacity_bytes: int,
        budget: ResidentByteBudget,
    ) -> None:
        super().__init__(
            request_id=request_id,
            attempt=1,
            capacity_bytes=capacity_bytes,
            budget=budget,
        )
        self.first_release_entered = asyncio.Event()
        self.continue_first_release = asyncio.Event()
        self.release_owners: list[object] = []

    async def release(self, lease: ResidentLease) -> None:
        self.release_owners.append(lease.owner)
        if len(self.release_owners) == 1:
            self.first_release_entered.set()
            await self.continue_first_release.wait()
        await super().release(lease)


@pytest.mark.parametrize("first_operation", ["acknowledge", "close"])
@pytest.mark.asyncio
async def test_pending_ack_and_close_serialize_rendered_lease_release(
    first_operation: str,
) -> None:
    budget = ResidentByteBudget(capacity_bytes=4096)
    account = _PausedReleaseAccount(
        request_id="request-ack-close-race",
        capacity_bytes=4096,
        budget=budget,
    )
    writer = _PendingWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
        resident_account=account,
    )
    (batch,) = await session.deliver(_block(0, TextBlock("race")))

    if first_operation == "acknowledge":
        acknowledgement = asyncio.create_task(
            session.acknowledge_data(batch.data, "accepted")
        )
        await account.first_release_entered.wait()
        close = asyncio.create_task(session.aclose())
        await asyncio.sleep(0)
        assert close.done() is False
    else:
        close = asyncio.create_task(session.aclose())
        await account.first_release_entered.wait()
        acknowledgement = asyncio.create_task(
            session.acknowledge_data(batch.data, "accepted")
        )
        await acknowledgement

    account.continue_first_release.set()
    await asyncio.gather(acknowledgement, close)

    rendered_release_count = sum(
        1
        for owner in account.release_owners
        if isinstance(owner, tuple)
        and cast(tuple[object, ...], owner)[0] == "rendered"
    )
    assert rendered_release_count == 1
    assert account.current_bytes == 0
    assert budget.current_bytes == 0
    await session.aclose()


@pytest.mark.asyncio
async def test_cancelled_close_does_not_interrupt_background_cleanup() -> None:
    budget = ResidentByteBudget(capacity_bytes=4096)
    account = _PausedReleaseAccount(
        request_id="request-cancelled-close",
        capacity_bytes=4096,
        budget=budget,
    )
    writer = _PendingWriter()
    session = DeliverySession(
        renderer=AnthropicSseRenderer(message_id="msg_delivery", model="gpt-test"),
        sink=_PendingSink(writer),
        resident_account=account,
    )
    await session.deliver(_block(0, TextBlock("cleanup")))
    cancelled_waiter = asyncio.create_task(session.aclose())
    await account.first_release_entered.wait()
    surviving_waiter = asyncio.create_task(session.aclose())
    await asyncio.sleep(0)

    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    account.continue_first_release.set()
    await surviving_waiter

    rendered_release_count = sum(
        1
        for owner in account.release_owners
        if isinstance(owner, tuple)
        and cast(tuple[object, ...], owner)[0] == "rendered"
    )
    assert rendered_release_count == 1
    assert account.current_bytes == 0
    assert budget.current_bytes == 0
    await session.aclose()