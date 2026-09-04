from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, cast

import anyio
import tiktoken
from anyio.to_process import run_sync

from app.model_provider.types import ModelDescriptor, PromptTokenLimits

OPENAI_RESPONSES = "openai-responses"
SUPPORTED_ADMISSION_TOKENIZERS = frozenset({"o200k_base"})

_ALLOWED_TOP_LEVEL = frozenset(
    {
        "background",
        "client_metadata",
        "context_management",
        "include",
        "input",
        "instructions",
        "max_output_tokens",
        "metadata",
        "model",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
        "safety_identifier",
        "service_tier",
        "store",
        "stream",
        "temperature",
        "text",
        "tool_choice",
        "tools",
        "top_p",
        "truncation",
        "user",
    }
)
_ALLOWED_ITEM_FIELDS = {
    "additional_tools": frozenset({"agent", "id", "role", "tools", "type"}),
    "function_call": frozenset(
        {"agent", "arguments", "call_id", "caller", "id", "name", "status", "type"}
    ),
    "function_call_output": frozenset(
        {"agent", "call_id", "caller", "id", "name", "output", "status", "type"}
    ),
    "message": frozenset({"agent", "content", "id", "role", "status", "type"}),
    "reasoning": frozenset({"agent", "encrypted_content", "id", "status", "summary", "type"}),
    "tool_search_call": frozenset(
        {"agent", "arguments", "call_id", "execution", "id", "status", "type"}
    ),
    "tool_search_output": frozenset(
        {"agent", "call_id", "execution", "id", "status", "tools", "type"}
    ),
}
_ALLOWED_TEXT_PART_FIELDS = frozenset({"annotations", "logprobs", "text", "type"})
_ALLOWED_IMAGE_PART_FIELDS = frozenset({"detail", "file_id", "image_url", "type"})
_ALLOWED_SUMMARY_FIELDS = frozenset({"text", "type"})


class TokenAdmissionOutcome(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SKIPPED_MISSING_METADATA = "skipped_missing_metadata"
    SKIPPED_UNSUPPORTED_TOKENIZER = "skipped_unsupported_tokenizer"
    SKIPPED_REDUCTION_CONTROL = "skipped_reduction_control"
    SKIPPED_UNKNOWN_SHAPE = "skipped_unknown_shape"
    ADMITTED_FAST = "admitted_fast"
    ADMITTED_COUNTED = "admitted_counted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TokenAdmissionObservation:
    attempt: int
    origin: Literal["proxy"]
    outcome: TokenAdmissionOutcome
    target_format: str
    model: str
    provider: str
    catalog_generation: int
    catalog_refreshed_at: str
    tokenizer: str | None = None
    max_prompt_tokens: int | None = None
    max_context_window_tokens: int | None = None
    field_path: str | None = None
    field_kind: str | None = None
    field_utf8_byte_count: int | None = None
    field_token_count: int | None = None


@dataclass(frozen=True, slots=True)
class _TextCandidate:
    path: str
    kind: str
    text: str
    utf8_bytes: int


def _count_ordinary(tokenizer: str, text: str) -> int | None:
    """Count one standalone field in a cancellable worker process.

    ``None`` means the runtime no longer recognises a name the admission registry did. Only lookup failure is converted; encoding failures and process failures remain errors.
    """
    try:
        encoding = tiktoken.get_encoding(tokenizer)
    except ValueError:
        return None
    return len(encoding.encode_ordinary(text))


def _candidate(path: str, kind: str, text: str) -> _TextCandidate:
    return _TextCandidate(path=path, kind=kind, text=text, utf8_bytes=len(text.encode("utf-8")))


def _unknown_fields(value: Mapping[str, Any], allowed: frozenset[str]) -> bool:
    return not set(value).issubset(allowed)


def _message_candidates(item: Mapping[str, Any], index: int) -> list[_TextCandidate] | None:
    content = item.get("content")
    path = f"input[{index}].content"
    if isinstance(content, str):
        return [_candidate(path, "message_content", content)]
    if not isinstance(content, list):
        return None
    candidates: list[_TextCandidate] = []
    for part_index, raw_part in enumerate(cast(list[Any], content)):
        if not isinstance(raw_part, Mapping):
            return None
        part = cast(Mapping[str, Any], raw_part)
        kind = part.get("type")
        part_path = f"{path}[{part_index}]"
        if kind in {"input_text", "output_text"}:
            if _unknown_fields(part, _ALLOWED_TEXT_PART_FIELDS):
                return None
            text = part.get("text")
            if not isinstance(text, str):
                return None
            candidates.append(_candidate(f"{part_path}.text", str(kind), text))
            continue
        if kind == "input_image":
            if _unknown_fields(part, _ALLOWED_IMAGE_PART_FIELDS):
                return None
            continue
        return None
    return candidates


def _reasoning_candidates(item: Mapping[str, Any], index: int) -> list[_TextCandidate] | None:
    summary = item.get("summary")
    if not isinstance(summary, list):
        return None
    candidates: list[_TextCandidate] = []
    for summary_index, raw_part in enumerate(cast(list[Any], summary)):
        if not isinstance(raw_part, Mapping):
            return None
        part = cast(Mapping[str, Any], raw_part)
        if part.get("type") != "summary_text" or _unknown_fields(part, _ALLOWED_SUMMARY_FIELDS):
            return None
        text = part.get("text")
        if not isinstance(text, str):
            return None
        candidates.append(
            _candidate(
                f"input[{index}].summary[{summary_index}].text",
                "reasoning_summary",
                text,
            )
        )
    return candidates


def _input_candidates(value: object) -> list[_TextCandidate] | None:
    if isinstance(value, str):
        return [_candidate("input", "input", value)]
    if not isinstance(value, list):
        return None
    candidates: list[_TextCandidate] = []
    for index, raw_item in enumerate(cast(list[Any], value)):
        if not isinstance(raw_item, Mapping):
            return None
        item = cast(Mapping[str, Any], raw_item)
        kind = item.get("type")
        if not isinstance(kind, str) or kind not in _ALLOWED_ITEM_FIELDS:
            return None
        if _unknown_fields(item, _ALLOWED_ITEM_FIELDS[kind]):
            return None
        if kind == "message":
            found = _message_candidates(item, index)
            if found is None:
                return None
            candidates.extend(found)
        elif kind == "function_call":
            arguments = item.get("arguments")
            if not isinstance(arguments, str):
                return None
            candidates.append(
                _candidate(f"input[{index}].arguments", "function_call_arguments", arguments)
            )
        elif kind == "function_call_output":
            output = item.get("output")
            if isinstance(output, str):
                candidates.append(
                    _candidate(f"input[{index}].output", "function_call_output", output)
                )
        elif kind == "reasoning":
            found = _reasoning_candidates(item, index)
            if found is None:
                return None
            candidates.extend(found)
    return candidates


def _shape_candidates(payload: Mapping[str, Any]) -> list[_TextCandidate] | None:
    if _unknown_fields(payload, _ALLOWED_TOP_LEVEL):
        return None
    candidates: list[_TextCandidate] = []
    if "instructions" in payload:
        instructions = payload.get("instructions")
        if not isinstance(instructions, str):
            return None
        candidates.append(_candidate("instructions", "instructions", instructions))
    if "input" in payload:
        found = _input_candidates(payload.get("input"))
        if found is None:
            return None
        candidates.extend(found)
    return candidates


def _is_compaction_item(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    item = cast(Mapping[str, Any], value)
    return item.get("type") in {"compaction", "compaction_trigger"}


def _has_reduction_control(payload: Mapping[str, Any]) -> bool:
    if "truncation" in payload and payload.get("truncation") != "disabled":
        return True
    if "context_management" in payload and payload.get("context_management") not in (None, []):
        return True
    items = payload.get("input")
    return bool(
        isinstance(items, list)
        and any(_is_compaction_item(item) for item in cast(list[Any], items))
    )


class PromptTokenAdmission:
    def __init__(self, *, limiter: anyio.CapacityLimiter | None = None) -> None:
        self._limiter = limiter or anyio.CapacityLimiter(1)

    @staticmethod
    def _observation(
        *,
        attempt: int,
        target_format: str,
        descriptor: ModelDescriptor,
        outcome: TokenAdmissionOutcome,
        limits: PromptTokenLimits | None = None,
        candidate: _TextCandidate | None = None,
        token_count: int | None = None,
    ) -> TokenAdmissionObservation:
        return TokenAdmissionObservation(
            attempt=attempt,
            origin="proxy",
            outcome=outcome,
            target_format=target_format,
            model=descriptor.id,
            provider=descriptor.provider_name,
            catalog_generation=descriptor.catalog_generation,
            catalog_refreshed_at=descriptor.catalog_refreshed_at,
            tokenizer=limits.tokenizer if limits is not None else None,
            max_prompt_tokens=limits.max_prompt_tokens if limits is not None else None,
            max_context_window_tokens=(
                limits.max_context_window_tokens if limits is not None else None
            ),
            field_path=candidate.path if candidate is not None else None,
            field_kind=candidate.kind if candidate is not None else None,
            field_utf8_byte_count=candidate.utf8_bytes if candidate is not None else None,
            field_token_count=token_count,
        )

    async def evaluate(
        self,
        *,
        attempt: int,
        target_format: str,
        descriptor: ModelDescriptor,
        payload: Mapping[str, Any],
    ) -> TokenAdmissionObservation:
        if target_format != OPENAI_RESPONSES:
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.NOT_APPLICABLE,
            )
        limits = descriptor.prompt_token_limits
        if limits is None:
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.SKIPPED_MISSING_METADATA,
            )
        if limits.tokenizer not in SUPPORTED_ADMISSION_TOKENIZERS:
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.SKIPPED_UNSUPPORTED_TOKENIZER,
                limits=limits,
            )
        if _has_reduction_control(payload):
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.SKIPPED_REDUCTION_CONTROL,
                limits=limits,
            )
        candidates = _shape_candidates(payload)
        if candidates is None:
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.SKIPPED_UNKNOWN_SHAPE,
                limits=limits,
            )
        largest = max(candidates, key=lambda item: item.utf8_bytes, default=None)
        to_count = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.utf8_bytes > limits.max_context_window_tokens
            ),
            key=lambda item: item.utf8_bytes,
            reverse=True,
        )
        if not to_count:
            return self._observation(
                attempt=attempt,
                target_format=target_format,
                descriptor=descriptor,
                outcome=TokenAdmissionOutcome.ADMITTED_FAST,
                limits=limits,
                candidate=largest,
            )
        largest_counted: tuple[_TextCandidate, int] | None = None
        for candidate in to_count:
            count = await run_sync(
                _count_ordinary,
                limits.tokenizer,
                candidate.text,
                cancellable=True,
                limiter=self._limiter,
            )
            if count is None:
                return self._observation(
                    attempt=attempt,
                    target_format=target_format,
                    descriptor=descriptor,
                    outcome=TokenAdmissionOutcome.SKIPPED_UNSUPPORTED_TOKENIZER,
                    limits=limits,
                )
            if count > limits.max_context_window_tokens:
                return self._observation(
                    attempt=attempt,
                    target_format=target_format,
                    descriptor=descriptor,
                    outcome=TokenAdmissionOutcome.REJECTED,
                    limits=limits,
                    candidate=candidate,
                    token_count=count,
                )
            if largest_counted is None or count > largest_counted[1]:
                largest_counted = (candidate, count)
        assert largest_counted is not None
        return self._observation(
            attempt=attempt,
            target_format=target_format,
            descriptor=descriptor,
            outcome=TokenAdmissionOutcome.ADMITTED_COUNTED,
            limits=limits,
            candidate=largest_counted[0],
            token_count=largest_counted[1],
        )


__all__ = [
    "OPENAI_RESPONSES",
    "PromptTokenAdmission",
    "TokenAdmissionObservation",
    "TokenAdmissionOutcome",
]
