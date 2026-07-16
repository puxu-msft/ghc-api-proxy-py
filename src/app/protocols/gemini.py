import json
from typing import Any, cast

from app.models.gemini import GenerateContentRequest

GEMINI_METHODS = frozenset({"generateContent", "streamGenerateContent", "countTokens"})


class GeminiPathError(ValueError):
    pass


def parse_model_with_method(value: str) -> tuple[str, str]:
    model, separator, method = value.rpartition(":")
    if not separator or not model or method not in GEMINI_METHODS:
        raise GeminiPathError(f"Invalid Gemini model method: {value}")
    return model, method


def _content_text(parts: list[Any]) -> str:
    return "".join(part.text or "" for part in parts if getattr(part, "text", None))


def gemini_to_openai(
    request: GenerateContentRequest,
    *,
    model: str,
    stream: bool,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if request.system_instruction:
        messages.append(
            {"role": "system", "content": _content_text(request.system_instruction.parts)}
        )
    for content in request.contents:
        role = "assistant" if content.role == "model" else "user"
        text = _content_text(content.parts)
        tool_calls = [part.function_call for part in content.parts if part.function_call]
        tool_results = [part.function_response for part in content.parts if part.function_response]
        if tool_results:
            for result_part in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result_part.get("name"),
                        "content": str(result_part.get("response", "")),
                    }
                )
        else:
            message: dict[str, Any] = {"role": role, "content": text or None}
            if tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.get("name"),
                        "type": "function",
                        "function": {
                            "name": call.get("name"),
                            "arguments": json.dumps(call.get("args", {})),
                        },
                    }
                    for call in tool_calls
                ]
            messages.append(message)
    result: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
    if request.tools:
        result["tools"] = [
            {
                "type": "function",
                "function": declaration.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
            }
            for tool in request.tools
            for declaration in (tool.function_declarations or [])
        ]
    config = request.generation_config
    if config:
        for target, value in (
            ("temperature", config.temperature),
            ("top_p", config.top_p),
            ("max_tokens", config.max_output_tokens),
            ("stop", config.stop_sequences),
        ):
            if value is not None:
                result[target] = value
    return result


def openai_to_gemini(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices", [])
    text = ""
    finish_reason = None
    if choices:
        choice = cast(dict[str, Any], choices[0])
        message = cast(dict[str, Any], choice.get("message", {}))
        text = message.get("content") or ""
        finish_reason = choice.get("finish_reason")
        tool_calls = cast(list[dict[str, Any]], message.get("tool_calls", []))
    else:
        tool_calls = []
    usage = data.get("usage", {})
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        *([{"text": text}] if text else []),
                        *[_tool_call_part(call) for call in tool_calls],
                    ],
                },
                "finishReason": finish_reason,
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": usage.get("prompt_tokens", 0),
            "candidatesTokenCount": usage.get("completion_tokens", 0),
            "totalTokenCount": usage.get("total_tokens", 0),
        },
    }


def _tool_call_part(call: dict[str, Any]) -> dict[str, Any]:
    function = cast(dict[str, Any], call.get("function", {}))
    arguments = function.get("arguments", "{}")
    return {
        "functionCall": {
            "name": function.get("name"),
            "args": json.loads(arguments if isinstance(arguments, str) else "{}"),
        }
    }