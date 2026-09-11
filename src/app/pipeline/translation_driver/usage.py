"""Normalize OpenAI Responses usage at the translation seam.

The buffered response codec, the streaming delivery assembler, and response
observation all need the same conversion. Keeping it here prevents one path
from treating cached input as fresh input while another path reports the
correct Anthropic accounting.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Never, cast

from app.models.anthropic import AnthropicUsage


@dataclass(frozen=True, slots=True)
class ResponseConversionFact:
    code: str
    field_path: str


@dataclass(frozen=True, slots=True)
class ResponseUsageFacts:
    """Exact Responses usage details plus normalized Anthropic totals."""

    upstream_input_tokens: int
    input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    output_tokens: int
    reasoning_tokens: int | None
    total_tokens: int
    input_tokens_details: Mapping[str, int]
    output_tokens_details: Mapping[str, int]
    upstream_total_tokens: int | None = None
    inconsistent: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_tokens_details",
            MappingProxyType(dict(self.input_tokens_details)),
        )
        object.__setattr__(
            self,
            "output_tokens_details",
            MappingProxyType(dict(self.output_tokens_details)),
        )


class ResponsesUsageError(ValueError):
    def __init__(self, message: str, *, code: str, field_path: str) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path


@dataclass(frozen=True, slots=True)
class ResponseUsageConversion:
    wire: AnthropicUsage
    exact: ResponseUsageFacts | None
    facts: tuple[ResponseConversionFact, ...]


def anthropic_usage_from_responses(usage: object) -> dict[str, int]:
    """Return Responses usage using the Anthropic wire field names."""
    return convert_responses_usage(usage).wire.model_dump()


def convert_responses_usage(value: object) -> ResponseUsageConversion:
    if value is None:
        return ResponseUsageConversion(
            wire=AnthropicUsage(),
            exact=None,
            facts=(ResponseConversionFact(code="usage_estimated", field_path="usage"),),
        )

    usage = _mapping(value, "usage")
    total_input = _non_negative_integer(usage, "input_tokens", "usage.input_tokens")
    output = _non_negative_integer(usage, "output_tokens", "usage.output_tokens")
    upstream_total = _optional_non_negative_integer_or_none(
        usage,
        "total_tokens",
        "usage.total_tokens",
    )
    input_details = _usage_details(
        usage.get("input_tokens_details"),
        "usage.input_tokens_details",
    )
    output_details = _usage_details(
        usage.get("output_tokens_details"),
        "usage.output_tokens_details",
    )
    cache_read_observed = input_details.get("cached_tokens")
    cache_creation_observed = input_details.get("cache_write_tokens")
    reasoning_observed = output_details.get("reasoning_tokens")
    cache_read = cache_read_observed or 0
    cache_creation = cache_creation_observed or 0
    reasoning = reasoning_observed or 0
    wire_input_tokens = max(0, total_input - cache_read - cache_creation)
    has_cache_breakdown = (
        cache_read_observed is not None or cache_creation_observed is not None
    )
    exact_input_tokens = wire_input_tokens if has_cache_breakdown else None
    total_tokens = total_input + output

    facts: list[ResponseConversionFact] = []
    if total_input < cache_read + cache_creation:
        facts.append(
            ResponseConversionFact(
                code="usage_inconsistent",
                field_path="usage.input_tokens",
            )
        )
    if reasoning > output:
        facts.append(
            ResponseConversionFact(
                code="usage_inconsistent",
                field_path="usage.output_tokens_details.reasoning_tokens",
            )
        )
    if upstream_total is not None and upstream_total != total_input + output:
        facts.append(
            ResponseConversionFact(code="usage_inconsistent", field_path="usage.total_tokens")
        )

    return ResponseUsageConversion(
        wire=AnthropicUsage(
            input_tokens=wire_input_tokens,
            output_tokens=output,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
        exact=ResponseUsageFacts(
            upstream_input_tokens=total_input,
            input_tokens=exact_input_tokens,
            cache_read_input_tokens=cache_read_observed,
            cache_creation_input_tokens=cache_creation_observed,
            output_tokens=output,
            reasoning_tokens=reasoning_observed,
            total_tokens=total_tokens,
            input_tokens_details=input_details,
            output_tokens_details=output_details,
            upstream_total_tokens=upstream_total,
            inconsistent=bool(facts),
        ),
        facts=tuple(facts),
    )


def _usage_details(value: object, field_path: str) -> Mapping[str, int]:
    if value is None:
        return MappingProxyType({})
    details = _mapping(value, field_path)
    converted: dict[str, int] = {}
    for key, candidate in details.items():
        converted[key] = _non_negative_integer_value(candidate, f"{field_path}.{key}")
    return MappingProxyType(converted)


def _mapping(value: object, field_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field_path, "invalid_response", f"{field_path} must be an object")
    return cast(Mapping[str, Any], value)


def _non_negative_integer(value: Mapping[str, Any], key: str, field_path: str) -> int:
    return _non_negative_integer_value(value.get(key), field_path)


def _non_negative_integer_value(candidate: object, field_path: str) -> int:
    if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate < 0:
        _fail(field_path, "invalid_usage", f"{field_path} must be a non-negative integer")
    return candidate


def _optional_non_negative_integer_or_none(
    value: Mapping[str, Any], key: str, field_path: str
) -> int | None:
    if key not in value or value[key] is None:
        return None
    return _non_negative_integer(value, key, field_path)


def _fail(field_path: str, code: str, message: str) -> Never:
    raise ResponsesUsageError(message, code=code, field_path=field_path)


__all__ = [
    "ResponseConversionFact",
    "ResponseUsageConversion",
    "ResponseUsageFacts",
    "ResponsesUsageError",
    "anthropic_usage_from_responses",
    "convert_responses_usage",
]
