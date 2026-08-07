from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal, Protocol, cast

import orjson

from app.anthropic.thinking.reasoning_carrier import encode_reasoning_carrier
from app.openai.responses_stream_parser import (
    BlockIdentity,
    CompletedBlock,
    FunctionCallBlock,
    ReasoningBlock,
    ResponsesSemanticEvent,
    ResponsesTerminal,
    SourceOpened,
    TextBlock,
    UnsupportedResponsesEvent,
)
from app.streaming.sse import format_sse_event

type BatchKind = Literal["block", "terminal"]


class DeliveryOrderError(ValueError):
    """Raised when completed blocks cannot form one monotonic source prefix."""


class ResponsesDeliveryError(RuntimeError):
    """Typed refusal to turn an unsuccessful Responses lifecycle into success SSE."""

    def __init__(
        self,
        terminal: ResponsesTerminal | None,
        *,
        kind: str | None = None,
        code: str | None = None,
        message: str | None = None,
        open_blocks: tuple[BlockIdentity, ...] = (),
    ) -> None:
        self.kind = kind or (terminal.kind if terminal is not None else "delivery_error")
        self.code = code if code is not None else (
            terminal.error_code if terminal is not None else None
        )
        self.response_id = terminal.response_id if terminal is not None else None
        self.status = terminal.status if terminal is not None else None
        self.open_blocks = (
            open_blocks
            if open_blocks
            else (terminal.open_blocks if terminal is not None else ())
        )
        detail = message if message is not None else (
            terminal.message if terminal is not None else None
        )
        super().__init__(detail or self.code or self.kind)


class SingleWriterViolation(RuntimeError):
    """Raised when more than one writer attempts to own a delivery sink."""


@dataclass(frozen=True, slots=True)
class TerminalUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.input_tokens,
            self.output_tokens,
            self.cache_creation_input_tokens,
            self.cache_read_input_tokens,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("terminal usage values must be non-negative integers")

    def as_wire(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass(frozen=True, order=True, slots=True)
class BlockOrderKey:
    """Stable semantic order for blocks produced by one item-level source."""

    source_order: int
    part_order: int
    semantic_kind_order: int

    @classmethod
    def from_block(cls, block: CompletedBlock) -> BlockOrderKey:
        content = block.content
        if isinstance(content, ReasoningBlock):
            semantic_kind_order = 0
        elif isinstance(content, TextBlock):
            semantic_kind_order = 1
        else:
            semantic_kind_order = 2
        return cls(
            source_order=block.first_observed_order,
            part_order=(
                block.identity.content_index
                if block.identity.content_index is not None
                else 0
            ),
            semantic_kind_order=semantic_kind_order,
        )


@dataclass(frozen=True, slots=True)
class RenderedBatch:
    kind: BatchKind
    data: bytes
    includes_message_start: bool = False
    block_index: int | None = None
    order_key: BlockOrderKey | None = None

    @property
    def source_order(self) -> int | None:
        return self.order_key.source_order if self.order_key is not None else None

    @property
    def digest(self) -> str:
        return sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class CommittedBlock:
    identity: BlockIdentity
    order_key: BlockOrderKey
    block_index: int
    batch_digest: str

    @property
    def source_order(self) -> int:
        return self.order_key.source_order


class DeliveryWriter(Protocol):
    async def write(self, batch: bytes) -> None: ...


class DeliverySink(Protocol):
    def open_writer(self) -> DeliveryWriter: ...


class _InMemoryWriter:
    def __init__(self, batches: list[bytes]) -> None:
        self._batches = batches

    async def write(self, batch: bytes) -> None:
        self._batches.append(batch)


class InMemoryDeliverySink:
    """Memory sink that grants exactly one writer for its entire lifetime."""

    def __init__(self) -> None:
        self._batches: list[bytes] = []
        self._writer_opened = False

    @property
    def batches(self) -> tuple[bytes, ...]:
        return tuple(self._batches)

    def open_writer(self) -> DeliveryWriter:
        if self._writer_opened:
            raise SingleWriterViolation("delivery sink already has a writer")
        self._writer_opened = True
        return _InMemoryWriter(self._batches)


@dataclass(slots=True)
class _SourceState:
    identity: BlockIdentity
    open: bool = True
    blocks: dict[BlockOrderKey, CompletedBlock] = field(
        default_factory=lambda: dict[BlockOrderKey, CompletedBlock]()
    )


class ContinuousPrefixSequencer:
    """Release all blocks of each closed item source as one dense ordered prefix."""

    def __init__(self) -> None:
        self._next_source_order = 0
        self._sources: dict[int, _SourceState] = {}
        self._delivered_identities: set[BlockIdentity] = set()

    @property
    def next_source_order(self) -> int:
        return self._next_source_order

    @property
    def pending_source_orders(self) -> tuple[int, ...]:
        return tuple(sorted(self._sources))

    @property
    def open_source_orders(self) -> tuple[int, ...]:
        return tuple(sorted(order for order, state in self._sources.items() if state.open))

    def open_source(self, opened: SourceOpened) -> None:
        source_order = opened.source_order
        if source_order < self._next_source_order or source_order in self._sources:
            raise DeliveryOrderError(f"source order {source_order} was already opened")
        self._sources[source_order] = _SourceState(opened.identity)

    def push(self, block: CompletedBlock) -> None:
        source_order = block.first_observed_order
        state = self._sources.get(source_order)
        if state is None:
            raise DeliveryOrderError(f"block references unopened source order {source_order}")
        if not state.open:
            raise DeliveryOrderError(f"source order {source_order} was already closed")
        if (
            state.identity.output_index != block.identity.output_index
            or state.identity.item_id != block.identity.item_id
        ):
            raise DeliveryOrderError("block identity does not match its opened source")
        if block.identity in self._delivered_identities:
            raise DeliveryOrderError("block identity was already delivered")
        key = BlockOrderKey.from_block(block)
        blocks = state.blocks
        if key in blocks or any(
            pending.identity == block.identity for pending in blocks.values()
        ):
            raise DeliveryOrderError("block order key or identity was already observed")
        blocks[key] = block

    def reconcile_open_identities(
        self, open_identities: tuple[BlockIdentity, ...]
    ) -> tuple[CompletedBlock, ...]:
        open_items = {
            (identity.output_index, identity.item_id) for identity in open_identities
        }
        for state in self._sources.values():
            state.open = (state.identity.output_index, state.identity.item_id) in open_items

        ready: list[CompletedBlock] = []
        while (
            (state := self._sources.get(self._next_source_order)) is not None
            and not state.open
        ):
            blocks = state.blocks
            ordered = [blocks[key] for key in sorted(blocks)]
            ready.extend(ordered)
            self._delivered_identities.update(block.identity for block in ordered)
            del self._sources[self._next_source_order]
            self._next_source_order += 1
        return tuple(ready)


class DeliveryFrontier:
    """Accepted downstream envelopes; assembly and rendering do not advance it."""

    def __init__(self) -> None:
        self._message_start_accepted = False
        self._committed_blocks: list[CommittedBlock] = []
        self._terminal_accepted = False

    @property
    def message_start_accepted(self) -> bool:
        return self._message_start_accepted

    @property
    def committed_blocks(self) -> tuple[CommittedBlock, ...]:
        return tuple(self._committed_blocks)

    @property
    def terminal_accepted(self) -> bool:
        return self._terminal_accepted

    def accept_block(self, block: CompletedBlock, batch: RenderedBatch) -> None:
        expected_index = len(self._committed_blocks)
        if self._terminal_accepted:
            raise DeliveryOrderError("cannot accept a block after terminal")
        if batch.kind != "block" or batch.block_index != expected_index:
            raise DeliveryOrderError("block batch does not match the delivery frontier")
        order_key = BlockOrderKey.from_block(block)
        if batch.order_key != order_key:
            raise DeliveryOrderError("block batch order key does not match its source")
        if batch.includes_message_start:
            if self._message_start_accepted or expected_index != 0:
                raise DeliveryOrderError("message_start can only accompany the first block")
            self._message_start_accepted = True
        elif not self._message_start_accepted:
            raise DeliveryOrderError("the first block must include message_start")
        self._committed_blocks.append(
            CommittedBlock(
                identity=block.identity,
                order_key=order_key,
                block_index=expected_index,
                batch_digest=batch.digest,
            )
        )

    def accept_terminal(self, batch: RenderedBatch) -> None:
        if self._terminal_accepted:
            raise DeliveryOrderError("terminal was already accepted")
        if batch.kind != "terminal":
            raise DeliveryOrderError("expected a terminal batch")
        if batch.includes_message_start:
            if self._message_start_accepted or self._committed_blocks:
                raise DeliveryOrderError("terminal can start only an empty message")
            self._message_start_accepted = True
        elif not self._message_start_accepted:
            raise DeliveryOrderError("terminal requires an accepted message_start")
        self._terminal_accepted = True


class AnthropicSseRenderer:
    """Render immutable completed blocks into fully materialized Anthropic SSE batches."""

    def __init__(self, *, message_id: str, model: str) -> None:
        if not message_id or not model:
            raise ValueError("message_id and model are required")
        self._message_id = message_id
        self._model = model

    def render_block(
        self,
        block: CompletedBlock,
        *,
        block_index: int,
        include_message_start: bool,
    ) -> RenderedBatch:
        events: list[bytes] = []
        if include_message_start:
            events.append(self._message_start())
        events.extend(self._block_events(block, block_index))
        return RenderedBatch(
            kind="block",
            data=b"".join(events),
            includes_message_start=include_message_start,
            block_index=block_index,
            order_key=BlockOrderKey.from_block(block),
        )

    def render_terminal(
        self,
        *,
        stop_reason: str,
        usage: TerminalUsage,
        include_message_start: bool,
    ) -> RenderedBatch:
        events: list[bytes] = []
        if include_message_start:
            events.append(self._message_start())
        events.extend(
            (
                _event(
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                        "usage": usage.as_wire(),
                    },
                ),
                _event("message_stop", {"type": "message_stop"}),
            )
        )
        return RenderedBatch(
            kind="terminal",
            data=b"".join(events),
            includes_message_start=include_message_start,
        )

    def _message_start(self) -> bytes:
        return _event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": self._message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": self._model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        )

    def _block_events(self, block: CompletedBlock, block_index: int) -> tuple[bytes, ...]:
        content = block.content
        if isinstance(content, TextBlock):
            events = [
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            ]
            if content.text:
                events.append(
                    _event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {"type": "text_delta", "text": content.text},
                        },
                    )
                )
        elif isinstance(content, FunctionCallBlock):
            parsed = orjson.loads(content.arguments)
            if not isinstance(parsed, dict):
                raise ValueError("function-call arguments must decode to an object")
            cast(Mapping[str, Any], parsed)
            events = [
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": content.call_id,
                            "name": content.name,
                            "input": {},
                        },
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": content.arguments,
                        },
                    },
                ),
            ]
        else:
            signature = encode_reasoning_carrier(content.encrypted_content)
            events = [
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "thinking",
                            "thinking": "",
                            "signature": "",
                        },
                    },
                )
            ]
            if content.summary:
                events.append(
                    _event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {
                                "type": "thinking_delta",
                                "thinking": content.summary,
                            },
                        },
                    )
                )
            events.append(
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {"type": "signature_delta", "signature": signature},
                    },
                )
            )
        events.append(
            _event(
                "content_block_stop",
                {"type": "content_block_stop", "index": block_index},
            )
        )
        return tuple(events)


class DeliverySession:
    """Single-writer owner for typed parser facts, rendering, sinking, and commits."""

    def __init__(self, *, renderer: AnthropicSseRenderer, sink: DeliverySink) -> None:
        self._renderer = renderer
        self._writer = sink.open_writer()
        self._sequencer = ContinuousPrefixSequencer()
        self._operation_lock = asyncio.Lock()
        self._stopped_error: ResponsesDeliveryError | None = None
        self._terminal_fact: ResponsesTerminal | None = None
        self._mode: Literal["unset", "manual", "typed"] = "unset"
        self.frontier = DeliveryFrontier()

    @property
    def pending_source_orders(self) -> tuple[int, ...]:
        return self._sequencer.pending_source_orders

    async def deliver(self, block: CompletedBlock) -> tuple[RenderedBatch, ...]:
        """Compatibility helper for one-block-per-source callers.

        Parser-driven code must use ``consume`` so item lifecycle facts cannot be lost.
        """
        async with self._operation_lock:
            self._raise_if_stopped()
            self._select_mode("manual")
            identity = BlockIdentity(
                block.identity.output_index,
                block.identity.item_id,
                None,
            )
            self._sequencer.open_source(SourceOpened(identity, block.first_observed_order))
            self._sequencer.push(block)
            ready = self._sequencer.reconcile_open_identities(())
            return await self._write_ready(ready)

    async def consume(
        self,
        events: tuple[ResponsesSemanticEvent, ...],
        *,
        open_identities: tuple[BlockIdentity, ...],
        terminal_usage: TerminalUsage | None = None,
        stop_reason: str = "end_turn",
    ) -> tuple[RenderedBatch, ...]:
        """Atomically consume parser facts and emit only a closed successful prefix."""
        async with self._operation_lock:
            self._select_mode("typed")
            self._raise_if_stopped()
            if self.frontier.terminal_accepted:
                raise DeliveryOrderError("cannot consume events after terminal")
            terminal: ResponsesTerminal | None = None
            for event in events:
                if isinstance(event, SourceOpened):
                    self._sequencer.open_source(event)
                elif isinstance(event, CompletedBlock):
                    self._sequencer.push(event)
                elif isinstance(event, UnsupportedResponsesEvent):
                    error = self._unsupported(event)
                    self._stopped_error = error
                    raise error
                else:
                    if terminal is not None:
                        raise DeliveryOrderError("multiple terminal facts in one delivery step")
                    terminal = event

            if terminal is not None and terminal.open_blocks != open_identities:
                error = ResponsesDeliveryError(
                    terminal,
                    kind="delivery_error",
                    code="terminal_open_snapshot_mismatch",
                    message="terminal open blocks do not match the parser snapshot",
                    open_blocks=terminal.open_blocks or open_identities,
                )
                self._terminal_fact = terminal
                self._stopped_error = error
                raise error
            ready = self._sequencer.reconcile_open_identities(open_identities)
            accepted = list(await self._write_ready(ready))
            if terminal is not None:
                self._terminal_fact = terminal
                try:
                    accepted.append(
                        await self._finish_from_terminal(
                            terminal,
                            open_identities=open_identities,
                            stop_reason=stop_reason,
                            usage=terminal_usage,
                        )
                    )
                except ResponsesDeliveryError as error:
                    self._stopped_error = error
                    raise
            elif terminal_usage is not None:
                raise DeliveryOrderError("terminal usage requires a terminal fact")
            return tuple(accepted)

    async def _write_ready(
        self, ready: tuple[CompletedBlock, ...]
    ) -> tuple[RenderedBatch, ...]:
        if self.frontier.terminal_accepted:
            raise DeliveryOrderError("cannot deliver a block after terminal")
        accepted: list[RenderedBatch] = []
        for ready_block in ready:
            block_index = len(self.frontier.committed_blocks)
            batch = self._renderer.render_block(
                ready_block,
                block_index=block_index,
                include_message_start=not self.frontier.message_start_accepted,
            )
            await self._writer.write(batch.data)
            self.frontier.accept_block(ready_block, batch)
            accepted.append(batch)
        return tuple(accepted)

    async def finish(
        self,
        *,
        stop_reason: str,
        usage: TerminalUsage,
    ) -> RenderedBatch:
        """Finish a manually driven session; parser-driven callers use ``consume``."""
        async with self._operation_lock:
            self._raise_if_stopped()
            self._select_mode("manual")
            if self._sequencer.pending_source_orders:
                raise DeliveryOrderError("cannot accept terminal while a source remains")
            return await self._write_terminal(stop_reason=stop_reason, usage=usage)

    async def _finish_from_terminal(
        self,
        terminal: ResponsesTerminal,
        *,
        open_identities: tuple[BlockIdentity, ...],
        stop_reason: str,
        usage: TerminalUsage | None,
    ) -> RenderedBatch:
        if terminal.kind != "completed":
            raise ResponsesDeliveryError(terminal)
        if terminal.open_blocks or open_identities:
            raise ResponsesDeliveryError(
                terminal,
                kind="incomplete",
                code=terminal.error_code or "incomplete_lifecycle",
                message=terminal.message or "response terminal has open output items",
                open_blocks=terminal.open_blocks or open_identities,
            )
        if usage is None:
            raise ResponsesDeliveryError(
                terminal,
                kind="delivery_error",
                code="missing_terminal_usage",
                message="completed response requires terminal usage",
            )
        if self._sequencer.pending_source_orders or self._sequencer.open_source_orders:
            raise ResponsesDeliveryError(
                terminal,
                kind="delivery_error",
                code="uncommitted_source_prefix",
                message="completed response still has an uncommitted source prefix",
            )
        return await self._write_terminal(stop_reason=stop_reason, usage=usage)

    async def _write_terminal(
        self,
        *,
        stop_reason: str,
        usage: TerminalUsage,
    ) -> RenderedBatch:
        if self.frontier.terminal_accepted:
            raise DeliveryOrderError("terminal was already accepted")
        batch = self._renderer.render_terminal(
            stop_reason=stop_reason,
            usage=usage,
            include_message_start=not self.frontier.message_start_accepted,
        )
        await self._writer.write(batch.data)
        self.frontier.accept_terminal(batch)
        return batch

    @staticmethod
    def _unsupported(event: UnsupportedResponsesEvent) -> ResponsesDeliveryError:
        return ResponsesDeliveryError(
            None,
            kind="unsupported",
            code="unsupported_responses_event",
            message=f"unsupported Responses event: {event.event_type}",
        )

    def _raise_if_stopped(self) -> None:
        if self._stopped_error is not None:
            raise self._stopped_error
        if self._terminal_fact is not None:
            raise DeliveryOrderError("terminal fact was already consumed")

    def _select_mode(self, mode: Literal["manual", "typed"]) -> None:
        if self._mode == "unset":
            self._mode = mode
        elif self._mode != mode:
            raise DeliveryOrderError("manual and typed delivery APIs cannot be mixed")


def _event(event_type: str, payload: Mapping[str, Any]) -> bytes:
    return format_sse_event(orjson.dumps(payload).decode("utf-8"), event=event_type)


__all__ = [
    "AnthropicSseRenderer",
    "BlockOrderKey",
    "CommittedBlock",
    "ContinuousPrefixSequencer",
    "DeliveryFrontier",
    "DeliveryOrderError",
    "DeliverySession",
    "DeliverySink",
    "DeliveryWriter",
    "InMemoryDeliverySink",
    "RenderedBatch",
    "ResponsesDeliveryError",
    "SingleWriterViolation",
    "TerminalUsage",
]