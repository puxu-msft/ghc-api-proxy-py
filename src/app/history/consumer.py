import time
from collections.abc import Mapping
from typing import Any

from app.history.store import HistoryStore
from app.history.types import HistoryEntry, ModelRef
from app.pipeline.context import (
    RequestContext,
    RequestConversionFactRecord,
    RequestState,
    ResponseConversionFactRecord,
)


class HistoryConsumer:
    def __init__(self, store: HistoryStore) -> None:
        self._store = store

    async def started(self, context: RequestContext) -> None:
        entry = self._entry(context, "pending")
        self._store.in_flight.add(entry)
        await self._store.websockets.broadcast(
            {"type": "entry_added", "entry": {"id": entry.id, "status": entry.status}}
        )

    async def finalized(
        self,
        context: RequestContext,
        *,
        response: dict[str, Any] | None = None,
        usage: Mapping[str, int] | None = None,
        usage_estimated: bool = False,
    ) -> None:
        status = "completed" if context.state is RequestState.COMPLETED else "failed"
        entry = self._entry(context, status)
        if response is not None:
            entry.response = response
            if usage is not None:
                entry.usage = self._stream_usage_summary(
                    context,
                    usage,
                    estimated=usage_estimated,
                )
        elif context.state is RequestState.COMPLETED:
            if context.final_response_payload is not None:
                entry.response = context.final_response_payload
            entry.usage = self._usage_summary(context)
        await self._store.finalize(entry)
        await self._store.flush()
        self._store.in_flight.remove(entry.id)
        await self._store.websockets.broadcast(
            {"type": "entry_updated", "entry": {"id": entry.id, "status": entry.status}}
        )

    @staticmethod
    def _entry(context: RequestContext, status: str) -> HistoryEntry:
        return HistoryEntry(
            id=context.id,
            session_id=context.session_id,
            agent_id=context.agent_id or "main",
            started_at=context.created_at,
            ended_at=time.time() if status not in ("pending", "executing", "streaming") else None,
            endpoint=context.endpoint,
            status=status,
            model=ModelRef(
                context.original_model,
                context.resolved_model or context.original_model,
            ),
            request_payload=context.original_payload,
            error_message=context.error.message if context.error else None,
        )

    @staticmethod
    def _usage_summary(context: RequestContext) -> dict[str, Any] | None:
        response = context.normalized_response
        if response is None:
            return None
        exact = context.response_usage
        facts = HistoryConsumer._conversion_facts(context)
        estimated = any(
            isinstance(fact, ResponseConversionFactRecord)
            and fact.code == "usage_estimated"
            for fact in context.conversion_facts
        )
        if exact is None:
            usage = response.usage
            return {
                "input_tokens": usage.input_tokens if usage is not None else 0,
                "cache_read_input_tokens": (
                    usage.cache_read_input_tokens if usage is not None else 0
                ),
                "cache_creation_input_tokens": (
                    usage.cache_creation_input_tokens if usage is not None else 0
                ),
                "output_tokens": usage.output_tokens if usage is not None else 0,
                "reasoning_tokens": 0,
                "total_tokens": (
                    usage.input_tokens
                    + usage.cache_read_input_tokens
                    + usage.cache_creation_input_tokens
                    + usage.output_tokens
                    if usage is not None
                    else 0
                ),
                "estimated": estimated,
                "inconsistent": False,
                "conversion_facts": facts,
            }
        return {
            "input_tokens": exact.input_tokens,
            "cache_read_input_tokens": exact.cache_read_input_tokens,
            "cache_creation_input_tokens": exact.cache_creation_input_tokens,
            "upstream_input_tokens": exact.upstream_input_tokens,
            "output_tokens": exact.output_tokens,
            "reasoning_tokens": exact.reasoning_tokens,
            "total_tokens": exact.total_tokens,
            "upstream_total_tokens": exact.upstream_total_tokens,
            "input_tokens_details": dict(exact.input_tokens_details),
            "output_tokens_details": dict(exact.output_tokens_details),
            "estimated": estimated,
            "inconsistent": exact.inconsistent,
            "conversion_facts": facts,
        }

    @staticmethod
    def _conversion_facts(context: RequestContext) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for fact in context.conversion_facts:
            if isinstance(fact, RequestConversionFactRecord):
                facts.append(
                    {
                        "provenance": fact.provenance,
                        "attempt": fact.attempt,
                        "field_path": fact.field_path,
                        "disposition": fact.disposition,
                        "reason": fact.reason,
                    }
                )
            else:
                facts.append(
                    {
                        "provenance": fact.provenance,
                        "attempt": fact.attempt,
                        "code": fact.code,
                        "field_path": fact.field_path,
                    }
                )
        return facts

    @staticmethod
    def _stream_usage_summary(
        context: RequestContext,
        usage: Mapping[str, int],
        *,
        estimated: bool,
    ) -> dict[str, Any]:
        input_tokens = usage.get("input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return {
            "input_tokens": input_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
            "output_tokens": output_tokens,
            "reasoning_tokens": 0,
            "total_tokens": (
                input_tokens + cache_read + cache_creation + output_tokens
            ),
            "estimated": estimated,
            "inconsistent": False,
            "conversion_facts": HistoryConsumer._conversion_facts(context),
        }