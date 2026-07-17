from typing import Any

import tiktoken
from anyio.to_thread import run_sync

from app.models.anthropic import ContentBlock, MessagesRequest
from app.models.gemini import CountTokensRequest, GenerateContentRequest
from app.wire_json import dumps

_TOKENIZER_NAME = "o200k_base"


async def preload_tokenizer() -> None:
    await run_sync(tiktoken.get_encoding, _TOKENIZER_NAME)


def _anthropic_content_text(
    content: str | list[ContentBlock],
    *,
    assistant: bool,
) -> str:
    if isinstance(content, str):
        return content
    values: list[str] = []
    for block in content:
        if assistant and block.type in ("thinking", "redacted_thinking"):
            continue
        if block.text is not None:
            values.append(block.text)
        elif block.content is not None:
            values.append(
                block.content
                if isinstance(block.content, str)
                else dumps(
                    [item.model_dump(mode="json", exclude_none=True) for item in block.content]
                ).decode()
            )
        elif block.input is not None:
            values.append(dumps(block.input).decode())
        elif block.source is not None:
            values.append(dumps(block.source).decode())
    return "\n".join(values)


def estimate_anthropic_input(request: MessagesRequest) -> int:
    encoding = tiktoken.get_encoding(_TOKENIZER_NAME)
    total = 0
    if isinstance(request.system, str):
        total += len(encoding.encode(request.system)) + 4
    elif request.system:
        total += sum(len(encoding.encode(block.text)) + 4 for block in request.system)
    if request.tools:
        tool_data = [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]
        total += len(encoding.encode(dumps(tool_data).decode())) + 4
    for message in request.messages:
        total += len(encoding.encode(message.role))
        total += len(
            encoding.encode(
                _anthropic_content_text(
                    message.content,
                    assistant=message.role == "assistant",
                )
            )
        )
        total += 4
    return max(total, 1)


def _gemini_request(request: CountTokensRequest | GenerateContentRequest) -> GenerateContentRequest:
    if isinstance(request, GenerateContentRequest):
        return request
    if request.generate_content_request is not None:
        return request.generate_content_request
    return GenerateContentRequest(contents=request.contents or [])


def estimate_gemini_input(request: CountTokensRequest | GenerateContentRequest) -> int:
    payload = _gemini_request(request)
    values: list[str] = []
    if payload.system_instruction is not None:
        values.extend(_gemini_part_values(payload.system_instruction.parts))
    for content in payload.contents:
        if content.role:
            values.append(content.role)
        values.extend(_gemini_part_values(content.parts))
    if payload.tools:
        values.append(
            dumps(
                [
                    tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for tool in payload.tools
                ]
            ).decode()
        )
    encoding = tiktoken.get_encoding(_TOKENIZER_NAME)
    return max(len(encoding.encode("\n".join(values))), 1)


def _gemini_part_values(parts: list[Any]) -> list[str]:
    values: list[str] = []
    for part in parts:
        if part.text is not None:
            values.append(part.text)
        elif part.function_call is not None:
            values.append(dumps(part.function_call).decode())
        elif part.function_response is not None:
            values.append(dumps(part.function_response).decode())
        elif part.inline_data is not None:
            values.append(dumps(part.inline_data).decode())
    return values
