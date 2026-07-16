from typing import Any

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
        messages.append(
            {
                "role": "assistant" if content.role == "model" else "user",
                "content": _content_text(content.parts),
            }
        )
    result: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
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
        message = choices[0].get("message", {})
        text = message.get("content") or ""
        finish_reason = choices[0].get("finish_reason")
    usage = data.get("usage", {})
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": text}]},
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