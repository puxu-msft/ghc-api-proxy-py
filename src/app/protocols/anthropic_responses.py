from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Never, cast

import orjson
from pydantic import BaseModel, ValidationError

from app.anthropic.thinking.responses_reasoning import decode_anthropic_thinking
from app.models.anthropic import (
    AnthropicMessage,
    ContentBlock,
    MessagesRequest,
)

type JsonObject = dict[str, Any]
type Disposition = Literal["degrade"]

_REQUEST_FIELDS = frozenset(
    {
        "model",
        "messages",
        "max_tokens",
        "system",
        "stream",
        "temperature",
        "top_p",
        "top_k",
        "stop_sequences",
        "tools",
        "tool_choice",
        "thinking",
        "context_management",
        "metadata",
    }
)
_MESSAGE_FIELDS = frozenset({"role", "content"})
_SYSTEM_FIELDS = frozenset({"type", "text", "cache_control"})
_TOOL_FIELDS = frozenset(
    {"name", "description", "input_schema", "type", "cache_control", "defer_loading"}
)
_CONTENT_FIELDS_BY_TYPE = {
    "text": frozenset({"type", "text", "cache_control"}),
    "image": frozenset({"type", "source", "cache_control"}),
    "tool_use": frozenset({"type", "id", "name", "input", "cache_control"}),
    "tool_result": frozenset({"type", "tool_use_id", "content", "is_error", "cache_control"}),
    "thinking": frozenset({"type", "thinking", "signature", "cache_control"}),
    "redacted_thinking": frozenset({"type", "data", "cache_control"}),
}


@dataclass(frozen=True, slots=True)
class ConversionFact:
    field_path: str
    disposition: Disposition
    reason: str


@dataclass(frozen=True, slots=True)
class ReasoningEffortBand:
    max_budget_tokens: int | None
    effort: str


@dataclass(frozen=True, slots=True)
class ReasoningCapabilityFacts:
    supported_efforts: tuple[str, ...]
    budget_limits_known: bool
    min_budget_tokens: int | None
    max_budget_tokens: int | None
    enabled_budget_bands: tuple[ReasoningEffortBand, ...]
    adaptive_effort: str | None

    def __post_init__(self) -> None:
        supported = set(self.supported_efforts)
        if len(supported) != len(self.supported_efforts) or "" in supported:
            raise ValueError("supported reasoning efforts must be unique and non-empty")
        if (
            self.min_budget_tokens is not None
            and self.max_budget_tokens is not None
            and self.min_budget_tokens > self.max_budget_tokens
        ):
            raise ValueError("reasoning budget limits are reversed")
        finite_limits = [
            band.max_budget_tokens
            for band in self.enabled_budget_bands
            if band.max_budget_tokens is not None
        ]
        if finite_limits != sorted(finite_limits) or len(finite_limits) != len(set(finite_limits)):
            raise ValueError("reasoning effort bands must have increasing unique limits")
        if any(
            band.max_budget_tokens is None
            for band in self.enabled_budget_bands[:-1]
        ):
            raise ValueError("open-ended reasoning effort band must be last")
        if any(band.effort not in supported for band in self.enabled_budget_bands):
            raise ValueError("reasoning effort band is not supported")
        if self.adaptive_effort is not None and self.adaptive_effort not in supported:
            raise ValueError("adaptive reasoning effort is not supported")


@dataclass(frozen=True, slots=True)
class ToolNameMappingFact:
    original_name: str
    wire_name: str


class ToolNameMapper:
    def __init__(self, mappings: Mapping[str, str] | None = None) -> None:
        forward = dict(mappings or {})
        if any(not original or not wire for original, wire in forward.items()):
            raise ValueError("tool name mappings require non-empty names")
        self._forward = forward
        self._active_forward: dict[str, str] | None = None
        self._active_reverse: dict[str, str] | None = None

    def bind(self, names: set[str]) -> None:
        if self._active_forward is not None:
            raise ValueError("tool name mapper is already bound to a request")
        active_forward = {name: self._forward.get(name, name) for name in names}
        active_reverse = {wire: original for original, wire in active_forward.items()}
        if len(active_reverse) != len(active_forward):
            raise ValueError("tool name mappings collide within the request")
        self._active_forward = active_forward
        self._active_reverse = active_reverse

    def to_wire(self, name: str) -> str:
        if self._active_forward is None:
            return self._forward.get(name, name)
        return self._active_forward.get(name, name)

    def restore(self, name: str) -> str:
        if self._active_reverse is None:
            return name
        return self._active_reverse.get(name, name)

    @property
    def facts(self) -> tuple[ToolNameMappingFact, ...]:
        if self._active_forward is None:
            return ()
        return tuple(
            ToolNameMappingFact(original_name=original, wire_name=wire)
            for original, wire in sorted(self._active_forward.items())
            if original != wire
        )


@dataclass(frozen=True, slots=True)
class ConvertedRequest:
    wire: JsonObject
    facts: tuple[ConversionFact, ...] = ()
    tool_name_mapping: tuple[ToolNameMappingFact, ...] = ()


class RequestConversionError(ValueError):
    def __init__(self, message: str, *, code: str, field_path: str) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path


class _RequestConverter:
    def __init__(
        self,
        request: MessagesRequest,
        *,
        reasoning_capabilities: ReasoningCapabilityFacts | None,
        tool_name_mapper: ToolNameMapper,
    ) -> None:
        self.request = request
        self.reasoning_capabilities = reasoning_capabilities
        self.tool_name_mapper = tool_name_mapper
        self.facts: list[ConversionFact] = []

    def convert(self) -> ConvertedRequest:
        self._reject_extras(self.request, _REQUEST_FIELDS, "")
        self._reject_unsupported_request_fields()
        self._bind_tool_name_mapper()

        wire: JsonObject = {
            "model": self.request.model,
            "input": self._convert_messages(),
            "max_output_tokens": self.request.max_tokens,
            "stream": self.request.stream,
        }
        instructions = self._convert_system()
        if instructions is not None:
            wire["instructions"] = instructions
        if self.request.temperature is not None:
            wire["temperature"] = self.request.temperature
        if self.request.top_p is not None:
            wire["top_p"] = self.request.top_p
        reasoning = self._convert_reasoning()
        if reasoning is not None:
            wire["reasoning"] = reasoning

        tools = self._convert_tools()
        if tools:
            wire["tools"] = tools
        tool_choice = self._convert_tool_choice(tools)
        if tool_choice is not None:
            wire["tool_choice"] = tool_choice
        if self.request.tool_choice is not None:
            disable_parallel = self.request.tool_choice.get("disable_parallel_tool_use")
            if disable_parallel is not None:
                wire["parallel_tool_calls"] = not disable_parallel

        self._convert_metadata(wire)
        return ConvertedRequest(
            wire=wire,
            facts=tuple(self.facts),
            tool_name_mapping=self.tool_name_mapper.facts,
        )

    def _bind_tool_name_mapper(self) -> None:
        names = {tool.name for tool in self.request.tools or []}
        for message in self.request.messages:
            if not isinstance(message.content, list):
                continue
            names.update(
                block.name
                for block in message.content
                if block.type == "tool_use" and isinstance(block.name, str)
            )
        choice = self.request.tool_choice
        if choice is not None and choice.get("type") == "tool":
            choice_name = choice.get("name")
            if isinstance(choice_name, str):
                names.add(choice_name)
        try:
            self.tool_name_mapper.bind(names)
        except ValueError as error:
            self._fail("tool_names", "tool_name_collision", str(error))

    def _reject_unsupported_request_fields(self) -> None:
        unsupported = (
            ("top_k", self.request.top_k),
            ("stop_sequences", self.request.stop_sequences),
            ("context_management", self.request.context_management),
        )
        for field_path, value in unsupported:
            if value not in (None, [], {}):
                self._fail(
                    field_path,
                    "unsupported_field",
                    f"{field_path} has no conversion in the pure Responses request bridge",
                )

    def _convert_reasoning(self) -> JsonObject | None:
        thinking = self.request.thinking
        if thinking is None:
            return None
        self._reject_mapping_extras(
            thinking,
            {"type", "budget_tokens"},
            "thinking",
        )
        thinking_type = thinking.get("type")
        if thinking_type == "disabled":
            if "budget_tokens" in thinking:
                self._fail(
                    "thinking.budget_tokens",
                    "unsupported_field",
                    "disabled thinking does not accept budget_tokens",
                )
            return None
        if thinking_type not in ("enabled", "adaptive"):
            self._fail(
                "thinking.type",
                "unsupported_thinking",
                f"unsupported thinking type {thinking_type!r}",
            )

        budget: int | None = None
        if thinking_type == "enabled":
            candidate_budget = thinking.get("budget_tokens")
            if (
                not isinstance(candidate_budget, int)
                or isinstance(candidate_budget, bool)
                or candidate_budget <= 0
            ):
                self._fail(
                    "thinking.budget_tokens",
                    "invalid_thinking",
                    "enabled thinking requires a positive integer budget_tokens",
                )
            budget = candidate_budget

        capabilities = self.reasoning_capabilities
        if capabilities is None or not capabilities.supported_efforts:
            self._fail(
                "thinking",
                "reasoning_not_supported",
                "reasoning capability facts are required for enabled thinking",
            )

        if thinking_type == "adaptive":
            if "budget_tokens" in thinking:
                self._fail(
                    "thinking.budget_tokens",
                    "unsupported_field",
                    "adaptive thinking does not accept budget_tokens",
                )
            adaptive_effort = capabilities.adaptive_effort
            if (
                adaptive_effort is None
                or adaptive_effort not in capabilities.supported_efforts
            ):
                self._fail(
                    "thinking",
                    "reasoning_not_supported",
                    "adaptive thinking has no supported explicit effort",
                )
            return {"effort": adaptive_effort, "summary": "auto"}

        if not capabilities.budget_limits_known:
            self._fail(
                "thinking",
                "reasoning_not_supported",
                "reasoning budget capability limits are unknown",
            )
        assert budget is not None
        if (
            capabilities.min_budget_tokens is not None
            and budget < capabilities.min_budget_tokens
        ) or (
            capabilities.max_budget_tokens is not None
            and budget > capabilities.max_budget_tokens
        ):
            self._fail(
                "thinking.budget_tokens",
                "reasoning_budget_not_supported",
                "thinking budget is outside the model capability limits",
            )
        effort = next(
            (
                band.effort
                for band in capabilities.enabled_budget_bands
                if band.max_budget_tokens is None or budget <= band.max_budget_tokens
            ),
            None,
        )
        if effort is None or effort not in capabilities.supported_efforts:
            self._fail(
                "thinking.budget_tokens",
                "reasoning_budget_not_supported",
                "thinking budget has no supported explicit effort mapping",
            )
        return {"effort": effort, "summary": "auto"}

    def _convert_system(self) -> str | None:
        system = self.request.system
        if system is None:
            return None
        if isinstance(system, str):
            return system

        texts: list[str] = []
        for index, block in enumerate(system):
            path = f"system[{index}]"
            self._reject_extras(block, _SYSTEM_FIELDS, path)
            if block.type != "text":
                self._fail(
                    path,
                    "unsupported_system_block",
                    f"unsupported system block {block.type!r}",
                )
            if block.cache_control is not None:
                self._degrade(f"{path}.cache_control", "cache_control_not_supported")
            texts.append(block.text)
        return "\n\n".join(texts)

    def _convert_messages(self) -> list[JsonObject]:
        items: list[JsonObject] = []
        for message_index, message in enumerate(self.request.messages):
            path = f"messages[{message_index}]"
            self._reject_extras(message, _MESSAGE_FIELDS, path)
            if message.role not in ("user", "assistant"):
                self._fail(f"{path}.role", "unsupported_role", f"unsupported role {message.role!r}")
            if isinstance(message.content, list) and not message.content:
                self._fail(
                    f"{path}.content",
                    "invalid_content",
                    "message content list must not be empty",
                )
            if isinstance(message.content, str):
                items.append(self._text_message(message.role, [message.content]))
                continue
            items.extend(self._convert_blocks(message, message_index))
        return items

    def _convert_blocks(self, message: AnthropicMessage, message_index: int) -> list[JsonObject]:
        items: list[JsonObject] = []
        pending_parts: list[JsonObject] = []
        blocks = cast(list[ContentBlock], message.content)

        def flush_message() -> None:
            if pending_parts:
                items.append(
                    {"type": "message", "role": message.role, "content": list(pending_parts)}
                )
                pending_parts.clear()

        for block_index, block in enumerate(blocks):
            path = f"messages[{message_index}].content[{block_index}]"
            if self._is_server_block(block.type):
                self._fail(path, "server_tool_not_supported", "server tools are not revived")
            if block.type not in _CONTENT_FIELDS_BY_TYPE:
                self._fail(
                    path,
                    "unsupported_content_block",
                    f"unsupported content block {block.type!r}",
                )
            self._reject_content_fields(block, path)
            if block.cache_control is not None:
                self._degrade(f"{path}.cache_control", "cache_control_not_supported")

            if block.type == "text":
                if block.text is None:
                    self._fail(path, "invalid_content_block", "text block requires text")
                part_type = "input_text" if message.role == "user" else "output_text"
                pending_parts.append({"type": part_type, "text": block.text})
                continue

            if block.type == "image":
                if message.role != "user":
                    self._fail(path, "unsupported_content_block", "assistant image is unsupported")
                pending_parts.append(self._convert_image(block, path))
                continue

            flush_message()
            if block.type == "tool_use":
                if message.role != "assistant":
                    self._fail(
                        path, "unsupported_content_block", "tool_use requires assistant role"
                    )
                items.append(self._convert_tool_use(block, path))
            elif block.type == "tool_result":
                if message.role != "user":
                    self._fail(path, "unsupported_content_block", "tool_result requires user role")
                items.append(self._convert_tool_result(block, path))
            elif block.type == "thinking":
                if message.role != "assistant":
                    self._fail(
                        path, "unsupported_content_block", "thinking requires assistant role"
                    )
                reasoning = self._convert_thinking(block, path)
                if reasoning is not None:
                    items.append(reasoning)
            elif block.type == "redacted_thinking":
                self._degrade(path, "redacted_thinking_not_portable")

        flush_message()
        return items

    def _convert_image(self, block: ContentBlock, path: str) -> JsonObject:
        source = block.source
        if not isinstance(source, dict):
            self._fail(f"{path}.source", "invalid_image_source", "image source must be an object")
        source_type = source.get("type")
        if source_type == "base64":
            media_type = source.get("media_type")
            data = source.get("data")
            if not isinstance(media_type, str) or not isinstance(data, str):
                self._fail(
                    f"{path}.source",
                    "invalid_image_source",
                    "base64 image requires media_type and data",
                )
            image_url = f"data:{media_type};base64,{data}"
            allowed = {"type", "media_type", "data"}
        elif source_type == "url":
            image_url = source.get("url")
            if not isinstance(image_url, str):
                self._fail(f"{path}.source.url", "invalid_image_source", "URL image requires url")
            allowed = {"type", "url"}
        else:
            self._fail(
                f"{path}.source.type",
                "unsupported_image_source",
                f"unsupported image source {source_type!r}",
            )
        self._reject_mapping_extras(source, allowed, f"{path}.source")
        return {"type": "input_image", "image_url": image_url}

    def _convert_tool_use(self, block: ContentBlock, path: str) -> JsonObject:
        if not block.id or not block.name or block.input is None:
            self._fail(path, "invalid_tool_use", "tool_use requires id, name, and input")
        return {
            "type": "function_call",
            "call_id": block.id,
            "name": self.tool_name_mapper.to_wire(block.name),
            "arguments": orjson.dumps(block.input).decode(),
        }

    def _convert_tool_result(self, block: ContentBlock, path: str) -> JsonObject:
        if not block.tool_use_id:
            self._fail(path, "invalid_tool_result", "tool_result requires tool_use_id")
        content = block.content
        if isinstance(content, str):
            output = content
        elif isinstance(content, list):
            pieces: list[str] = []
            for index, part in enumerate(content):
                part_path = f"{path}.content[{index}]"
                self._reject_content_fields(part, part_path)
                if part.type != "text" or part.text is None:
                    self._fail(
                        part_path,
                        "unsupported_tool_result_content",
                        "multimodal tool results are unsupported",
                    )
                if part.cache_control is not None:
                    self._degrade(f"{part_path}.cache_control", "cache_control_not_supported")
                pieces.append(part.text)
            output = "".join(pieces)
        elif content is None:
            output = ""
        else:
            self._fail(f"{path}.content", "invalid_tool_result", "invalid tool_result content")
        if block.is_error:
            output = f"[tool_error] {output}"
        return {"type": "function_call_output", "call_id": block.tool_use_id, "output": output}

    def _convert_thinking(self, block: ContentBlock, path: str) -> JsonObject | None:
        decoded = decode_anthropic_thinking(block.model_dump(mode="python"))
        if decoded.item is None:
            self._degrade(path, decoded.classification or "thinking_signature_not_portable")
            return None
        return cast(JsonObject, decoded.item)

    def _convert_tools(self) -> list[JsonObject]:
        converted: list[JsonObject] = []
        for index, tool in enumerate(self.request.tools or []):
            path = f"tools[{index}]"
            self._reject_extras(tool, _TOOL_FIELDS, path)
            if tool.type is not None:
                self._fail(path, "server_tool_not_supported", "typed/server tools are not revived")
            if tool.defer_loading:
                self._fail(
                    f"{path}.defer_loading",
                    "unsupported_field",
                    "deferred tools are unsupported",
                )
            if tool.cache_control is not None:
                self._degrade(f"{path}.cache_control", "cache_control_not_supported")
            wire_name = self.tool_name_mapper.to_wire(tool.name)
            output: JsonObject = {"type": "function", "name": wire_name}
            if tool.description is not None:
                output["description"] = tool.description
            if tool.input_schema is not None:
                output["parameters"] = tool.input_schema
            converted.append(output)
        return converted

    def _convert_tool_choice(self, tools: list[JsonObject]) -> str | JsonObject | None:
        choice = self.request.tool_choice
        if choice is None:
            return None
        choice_type = choice.get("type")
        if choice_type == "auto":
            converted: str | JsonObject = "auto"
        elif choice_type == "any":
            if not tools:
                self._fail("tool_choice", "invalid_tool_choice", "any requires at least one tool")
            converted = "required"
        elif choice_type == "none":
            converted = "none"
        elif choice_type == "tool":
            name = choice.get("name")
            if not isinstance(name, str):
                self._fail("tool_choice.name", "invalid_tool_choice", "named tool is not declared")
            wire_name = self.tool_name_mapper.to_wire(name)
            if not any(tool["name"] == wire_name for tool in tools):
                self._fail("tool_choice.name", "invalid_tool_choice", "named tool is not declared")
            converted = {"type": "function", "name": wire_name}
        else:
            self._fail(
                "tool_choice.type",
                "unsupported_tool_choice",
                f"unsupported tool choice {choice_type!r}",
            )

        allowed = {"type", "name", "disable_parallel_tool_use"}
        self._reject_mapping_extras(choice, allowed, "tool_choice")
        disable_parallel = choice.get("disable_parallel_tool_use")
        if disable_parallel is not None and not isinstance(disable_parallel, bool):
            self._fail(
                "tool_choice.disable_parallel_tool_use",
                "invalid_tool_choice",
                "disable_parallel_tool_use must be boolean",
            )
        return converted

    def _convert_metadata(self, wire: JsonObject) -> None:
        metadata = self.request.metadata
        if metadata is None:
            return
        user_id = metadata.get("user_id")
        if user_id is not None:
            if not isinstance(user_id, str):
                self._fail(
                    "metadata.user_id",
                    "invalid_metadata",
                    "metadata.user_id must be a string",
                )
            wire["user"] = user_id
        for key in sorted(metadata.keys() - {"user_id"}):
            self._degrade(f"metadata.{key}", "metadata_not_allowlisted")

    @staticmethod
    def _text_message(role: str, texts: list[str]) -> JsonObject:
        part_type = "input_text" if role == "user" else "output_text"
        return {
            "type": "message",
            "role": role,
            "content": [{"type": part_type, "text": text} for text in texts],
        }

    @staticmethod
    def _is_server_block(block_type: str) -> bool:
        return block_type == "server_tool_use" or block_type.endswith("_tool_result")

    def _reject_extras(self, model: BaseModel, allowed: frozenset[str], field_path: str) -> None:
        provided = set(model.model_fields_set) | set(model.model_extra or {})
        extras = provided - allowed
        if extras:
            extra = sorted(extras)[0]
            path = f"{field_path}.{extra}" if field_path else extra
            self._fail(path, "unsupported_field", f"unsupported field {path!r}")

    def _reject_mapping_extras(
        self, value: Mapping[str, Any], allowed: set[str], field_path: str
    ) -> None:
        extras = value.keys() - allowed
        if extras:
            extra = sorted(extras)[0]
            path = f"{field_path}.{extra}"
            self._fail(path, "unsupported_field", f"unsupported field {path!r}")

    def _reject_content_fields(self, block: ContentBlock, field_path: str) -> None:
        allowed = _CONTENT_FIELDS_BY_TYPE.get(block.type)
        if allowed is None:
            self._fail(
                field_path,
                "unsupported_content_block",
                f"unsupported content block {block.type!r}",
            )
        provided = set(block.model_fields_set) | set(block.model_extra or {})
        unsupported = provided - allowed
        if unsupported:
            extra = sorted(unsupported)[0]
            path = f"{field_path}.{extra}"
            self._fail(path, "unsupported_field", f"unsupported field {path!r}")

    def _degrade(self, field_path: str, reason: str) -> None:
        self.facts.append(
            ConversionFact(field_path=field_path, disposition="degrade", reason=reason)
        )

    @staticmethod
    def _fail(field_path: str, code: str, message: str) -> Never:
        raise RequestConversionError(message, code=code, field_path=field_path)


def convert_messages_request_to_responses(
    request: MessagesRequest | Mapping[str, Any],
    *,
    reasoning_capabilities: ReasoningCapabilityFacts | None = None,
    tool_name_mapper: ToolNameMapper | None = None,
) -> ConvertedRequest:
    if not isinstance(request, MessagesRequest):
        try:
            request = MessagesRequest.model_validate(request)
        except ValidationError as error:
            raise RequestConversionError(
                "invalid Anthropic Messages request",
                code="invalid_request",
                field_path=_validation_error_path(error),
            ) from error
    return _RequestConverter(
        request,
        reasoning_capabilities=reasoning_capabilities,
        tool_name_mapper=tool_name_mapper or ToolNameMapper(),
    ).convert()


def _validation_error_path(error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    location = first.get("loc", ())
    if not location:
        return "$"
    path = ""
    for segment in location:
        if isinstance(segment, int):
            path += f"[{segment}]"
        else:
            path += f".{segment}" if path else str(segment)
    return path


__all__ = [
    "ConversionFact",
    "ConvertedRequest",
    "ReasoningCapabilityFacts",
    "ReasoningEffortBand",
    "RequestConversionError",
    "ToolNameMapper",
    "ToolNameMappingFact",
    "convert_messages_request_to_responses",
]
