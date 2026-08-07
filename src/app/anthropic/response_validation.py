from collections.abc import Mapping
from typing import Any, cast

from anthropic.types import Message as SdkMessage
from pydantic import RootModel, TypeAdapter, model_validator

type JsonObject = dict[str, Any]


class _StrictMessagesResponseWire(RootModel[JsonObject]):
    @model_validator(mode="before")
    @classmethod
    def validate_wire(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            raise ValueError("Anthropic response body must be an object")
        payload = dict(cast(Mapping[str, Any], value))
        if payload.get("type") != "message":
            raise ValueError("Anthropic response type must be explicitly set to 'message'")
        if payload.get("role") != "assistant":
            raise ValueError("Anthropic response role must be explicitly set to 'assistant'")

        validated = TypeAdapter(SdkMessage).validate_python(payload)
        raw_content = payload.get("content")
        if not isinstance(raw_content, list):
            raise ValueError("Anthropic response content must be a list")
        content = cast(list[object], raw_content)
        for index, (raw_block, validated_block) in enumerate(
            zip(content, validated.content, strict=True)
        ):
            if not isinstance(raw_block, Mapping):
                raise ValueError(f"Anthropic response content[{index}] must be an object")
            block = cast(Mapping[str, Any], raw_block)
            allowed = set(type(validated_block).model_fields)
            mixed_fields = block.keys() - allowed
            if mixed_fields:
                names = ", ".join(sorted(mixed_fields))
                raise ValueError(
                    f"Anthropic response content[{index}] has fields incompatible with "
                    f"type {validated_block.type!r}: {names}"
                )
        return payload


def validate_messages_response_wire(value: object) -> JsonObject:
    """Validate final client-visible bytes without filling omitted wire fields."""
    return _StrictMessagesResponseWire.model_validate(value).root


__all__ = ["validate_messages_response_wire"]