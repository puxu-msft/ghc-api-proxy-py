from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import orjson

from app.anthropic.thinking.reasoning_carrier import encode_reasoning_carrier
from app.delivery.anthropic_sse import (
    AnthropicSseRenderer,
    DeliveryFrontier,
    DeliveryOutcome,
    DeliverySession,
    DeliverySink,
    DeliveryWriter,
    ResponsesDeliveryError,
    TerminalUsage,
)
from app.delivery.reservation import RequestResidentAccount
from app.errors import ApiError, ErrorCategory
from app.openai.responses_stream_parser import (
    CompletedBlock,
    FunctionCallBlock,
    ResponsesStreamParser,
    ResponsesStreamProtocolError,
    ResponsesTerminal,
    TextBlock,
)
from app.protocols.responses_anthropic import anthropic_message_id_from_response_id
from app.streaming.openai_sse import parse_sse_json

type JsonObject = dict[str, Any]


class _BufferedWriter:
    def __init__(self, pending: list[bytes]) -> None:
        self._pending = pending

    async def write(self, batch: bytes) -> DeliveryOutcome:
        self._pending.append(batch)
        return "pending"


class _BufferedSink:
    """Request-local single-writer sink drained only at complete block boundaries."""

    def __init__(self) -> None:
        self._pending: list[bytes] = []
        self._opened = False

    def open_writer(self) -> DeliveryWriter:
        if self._opened:
            raise RuntimeError("Responses stream sink already has a writer")
        self._opened = True
        return _BufferedWriter(self._pending)

    def drain(self) -> tuple[bytes, ...]:
        batches = tuple(self._pending)
        self._pending.clear()
        return batches


@dataclass(slots=True)
class ResponsesAnthropicStreamState:
    frontier: DeliveryFrontier | None = None
    error: ApiError | None = None
    message_id: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    usage: TerminalUsage | None = None
    usage_estimated: bool = False
    delivery_session: DeliverySession | None = None
    _committed_response: dict[str, Any] | None = None

    def accept_headers(self) -> None:
        if self.frontier is None:
            raise RuntimeError("Responses stream has no delivery frontier")
        self.frontier.accept_headers()

    def mark_headers_uncertain(self) -> None:
        if self.frontier is None:
            raise RuntimeError("Responses stream has no delivery frontier")
        self.frontier.mark_headers_uncertain()

    async def mark_body_uncertain(self, batch: bytes) -> None:
        if self.delivery_session is None:
            raise RuntimeError("Responses stream has no delivery session")
        await self.delivery_session.acknowledge_data_if_pending(batch, "uncertain")

    @property
    def committed_response(self) -> dict[str, Any] | None:
        if self._committed_response is not None:
            return self._committed_response
        return self._project_committed_response()

    def freeze_committed_response(self) -> None:
        self._committed_response = self._project_committed_response()

    def _project_committed_response(self) -> dict[str, Any] | None:
        frontier = self.frontier
        if frontier is None or (
            not frontier.committed_blocks
            and not frontier.terminal_accepted
            and not frontier.delivery_uncertain
        ):
            return None
        blocks: list[dict[str, Any]] = []
        for committed in frontier.committed_blocks:
            blocks.append(self._project_block(committed.block))
        delivery: dict[str, Any] = {
            "complete": frontier.terminal_accepted,
            "uncertain": frontier.delivery_uncertain,
        }
        if frontier.delivery_uncertain:
            delivery.update(
                {
                    "headers_state": frontier.headers_state,
                    "message_start_state": frontier.message_start_state,
                    "terminal_state": frontier.terminal_state,
                    "uncertain_block_index": frontier.uncertain_block_index,
                    "possibly_visible_block": (
                        self._project_block(frontier.uncertain_block)
                        if frontier.uncertain_block is not None
                        else None
                    ),
                }
            )
        return {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "content": blocks,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "stop_sequence": None,
            "delivery": delivery,
        }

    @staticmethod
    def _project_block(block: CompletedBlock) -> dict[str, Any]:
        content = block.content
        if isinstance(content, FunctionCallBlock):
            return {
                "type": "tool_use",
                "id": content.call_id,
                "name": content.name,
                "input": cast(JsonObject, orjson.loads(content.arguments)),
            }
        if isinstance(content, TextBlock):
            return {"type": "text", "text": content.text}
        return {
            "type": "thinking",
            "thinking": content.summary,
            "signature": encode_reasoning_carrier(content.encrypted_content),
        }


async def render_responses_as_anthropic_sse(
    stream: AsyncIterator[bytes],
    *,
    model: str,
    state: ResponsesAnthropicStreamState | None = None,
    resident_account: RequestResidentAccount | None = None,
    require_stable_response_id: bool = True,
) -> AsyncIterator[bytes]:
    """Render a successful Responses SSE attempt as complete Anthropic block batches."""
    stream_state = state or ResponsesAnthropicStreamState()
    try:
        async for batch in _render_responses_as_anthropic_sse(
            stream,
            model=model,
            state=stream_state,
            resident_account=resident_account,
            require_stable_response_id=require_stable_response_id,
        ):
            yield batch
    finally:
        stream_state.freeze_committed_response()
        if stream_state.delivery_session is not None:
            await stream_state.delivery_session.aclose()


async def _render_responses_as_anthropic_sse(
    stream: AsyncIterator[bytes],
    *,
    model: str,
    state: ResponsesAnthropicStreamState,
    resident_account: RequestResidentAccount | None,
    require_stable_response_id: bool,
) -> AsyncIterator[bytes]:
    parser = ResponsesStreamParser(
        require_stable_response_id=require_stable_response_id
    )
    sink: _BufferedSink | None = None
    session: DeliverySession | None = None
    response_id: str | None = None
    has_tool_use = False
    pending_terminal: tuple[
        tuple[CompletedBlock | ResponsesTerminal, ...],
        TerminalUsage,
        bool,
        str,
    ] | None = None
    stream_state = state

    try:
        async for value in parse_sse_json(stream):
            if not isinstance(value, dict):
                raise _upstream_error(
                    "Responses SSE event must be a JSON object",
                    code="invalid_responses_event",
                )
            event = cast(JsonObject, value)
            event_type = event.get("type")
            if event_type == "response.created":
                if session is not None:
                    raise _upstream_error(
                        "Responses stream contains multiple response.created events",
                        code="duplicate_response_created",
                    )
                response = _required_mapping(event, "response", event_type)
                response_id = _required_string(response, "id", event_type)
                stream_state.message_id = anthropic_message_id_from_response_id(
                    response_id
                )
                stream_state.model = model
                sink = _BufferedSink()
                session = DeliverySession(
                    renderer=AnthropicSseRenderer(
                        message_id=anthropic_message_id_from_response_id(response_id),
                        model=model,
                    ),
                    sink=cast(DeliverySink, sink),
                    resident_account=resident_account,
                )
                stream_state.frontier = session.frontier
                stream_state.delivery_session = session

            if session is None or sink is None:
                raise _upstream_error(
                    "Responses stream must start with response.created",
                    code="missing_response_created",
                )

            semantic_events = parser.process(event)
            has_tool_use = has_tool_use or any(
                isinstance(fact, CompletedBlock)
                and isinstance(fact.content, FunctionCallBlock)
                for fact in semantic_events
            )
            terminal = next(
                (
                    fact
                    for fact in semantic_events
                    if isinstance(fact, ResponsesTerminal)
                ),
                None,
            )
            terminal_usage = (
                _terminal_usage(event, terminal)
                if terminal is not None
                and (
                    terminal.kind == "completed"
                    or (
                        terminal.kind == "incomplete"
                        and terminal.error_code == "max_output_tokens"
                    )
                )
                else None
            )
            stop_reason = (
                "max_tokens"
                if terminal is not None
                and terminal.kind == "incomplete"
                and terminal.error_code == "max_output_tokens"
                else "tool_use" if has_tool_use else "end_turn"
            )
            if terminal is not None and terminal_usage is not None:
                pending_terminal = (
                    cast(tuple[CompletedBlock | ResponsesTerminal, ...], semantic_events),
                    terminal_usage[0],
                    terminal_usage[1],
                    stop_reason,
                )
                continue
            await session.consume(
                semantic_events,
                open_identities=parser.open_blocks,
                terminal_usage=None,
                stop_reason=stop_reason,
            )
            async for batch in _drain_accepted(session, sink):
                yield batch
    except Exception as error:
        api_error = _normalize_stream_error(error)
        stream_state.error = api_error
        if (
            session is not None
            and sink is not None
            and session.frontier.message_start_accepted
        ):
            await session.render_error(
                error_type=api_error.wire_type,
                message=api_error.message,
                code=api_error.code,
            )
            async for batch in _drain_accepted(session, sink):
                yield batch
            return
        raise api_error from error
    if session is None:
        api_error = _upstream_error(
            "Responses stream ended before response.created",
            code="missing_response_created",
        )
        stream_state.error = api_error
        raise api_error
    if pending_terminal is not None:
        terminal_events, terminal_usage, usage_estimated, stop_reason = pending_terminal
        try:
            await session.consume(
                terminal_events,
                open_identities=parser.open_blocks,
                terminal_usage=terminal_usage,
                stop_reason=stop_reason,
            )
            stream_state.stop_reason = stop_reason
            stream_state.usage = terminal_usage
            stream_state.usage_estimated = usage_estimated
            if sink is None:
                raise RuntimeError("Responses delivery session lost its sink")
            async for batch in _drain_accepted(session, sink):
                yield batch
        except Exception as error:
            api_error = _normalize_stream_error(error)
            stream_state.error = api_error
            if session.frontier.message_start_accepted and sink is not None:
                await session.render_error(
                    error_type=api_error.wire_type,
                    message=api_error.message,
                    code=api_error.code,
                )
                async for batch in _drain_accepted(session, sink):
                    yield batch
                return
            raise api_error from error
    if not session.frontier.terminal_accepted:
        api_error = _upstream_error(
            "Responses stream ended before a successful terminal event",
            code="incomplete_responses_stream",
        )
        stream_state.error = api_error
        if session.frontier.message_start_accepted:
            await session.render_error(
                error_type=api_error.wire_type,
                message=api_error.message,
                code=api_error.code,
            )
            if sink is None:
                raise RuntimeError("Responses delivery session lost its sink")
            async for batch in _drain_accepted(session, sink):
                yield batch
            return
        raise api_error


async def _drain_accepted(
    session: DeliverySession,
    sink: _BufferedSink,
) -> AsyncIterator[bytes]:
    for batch in sink.drain():
        try:
            yield batch
        except BaseException:
            await session.acknowledge_data_if_pending(batch, "uncertain")
            raise
        else:
            await session.acknowledge_data(batch, "accepted")


def _normalize_stream_error(error: Exception) -> ApiError:
    if isinstance(error, ApiError):
        return error
    if isinstance(error, ResponsesStreamProtocolError):
        return _upstream_error(str(error), code=error.code)
    if isinstance(error, ResponsesDeliveryError):
        return _upstream_error(str(error), code=error.code or error.kind)
    if isinstance(error, orjson.JSONDecodeError):
        return _upstream_error(
            "Responses SSE data is not valid JSON",
            code="invalid_responses_event",
        )
    return _upstream_error(
        str(error) or "Responses stream conversion failed",
        code="responses_stream_conversion_error",
    )


def _terminal_usage(
    event: Mapping[str, Any],
    terminal: ResponsesTerminal,
) -> tuple[TerminalUsage, bool]:
    response = _required_mapping(event, "response", cast(str, event.get("type")))
    if terminal.response_id is None:
        raise _upstream_error(
            "successful Responses terminal requires a response id",
            code="invalid_terminal_usage",
        )
    usage_value = response.get("usage")
    if usage_value is None:
        return TerminalUsage(input_tokens=0, output_tokens=0), True
    if not isinstance(usage_value, Mapping):
        raise _upstream_error(
            f"{event.get('type')} requires object field usage",
            code="invalid_responses_event",
        )
    usage = cast(Mapping[str, Any], usage_value)
    upstream_input = _non_negative_int(usage, "input_tokens")
    output = _non_negative_int(usage, "output_tokens")
    input_details_value = usage.get("input_tokens_details")
    input_details: Mapping[str, Any] = (
        cast(Mapping[str, Any], input_details_value)
        if isinstance(input_details_value, Mapping)
        else dict[str, Any]()
    )
    cache_read = _optional_non_negative_int(input_details, "cached_tokens")
    cache_creation = _optional_non_negative_int(input_details, "cache_write_tokens")
    return (
        TerminalUsage(
            input_tokens=max(0, upstream_input - cache_read - cache_creation),
            output_tokens=output,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        ),
        False,
    )


def _required_mapping(
    value: Mapping[str, Any],
    key: str,
    event_type: str,
) -> Mapping[str, Any]:
    candidate = value.get(key)
    if not isinstance(candidate, Mapping):
        raise _upstream_error(
            f"{event_type} requires object field {key}",
            code="invalid_responses_event",
        )
    return cast(Mapping[str, Any], candidate)


def _required_string(
    value: Mapping[str, Any],
    key: str,
    event_type: str,
) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate:
        raise _upstream_error(
            f"{event_type} requires string field {key}",
            code="invalid_responses_event",
        )
    return candidate


def _non_negative_int(value: Mapping[str, Any], key: str) -> int:
    candidate = value.get(key)
    if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate < 0:
        raise _upstream_error(
            f"Responses terminal usage field {key} must be a non-negative integer",
            code="invalid_terminal_usage",
        )
    return candidate


def _optional_non_negative_int(value: Mapping[str, Any], key: str) -> int:
    if key not in value:
        return 0
    return _non_negative_int(value, key)


def _upstream_error(message: str, *, code: str) -> ApiError:
    return ApiError(
        message,
        category=ErrorCategory.UPSTREAM,
        status_code=502,
        code=code,
    )


__all__ = ["ResponsesAnthropicStreamState", "render_responses_as_anthropic_sse"]
