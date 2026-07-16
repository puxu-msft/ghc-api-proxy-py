from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
import tiktoken
from fastapi import APIRouter, Response

from app.deps import ApprovalGateDependency, OpenAIClientDependency
from app.models.gemini import CountTokensRequest, GenerateContentRequest
from app.models.openai import ChatCompletionRequest
from app.pipeline.protocol_guard import apply_approval_guard
from app.protocols.gemini import (
    GeminiPathError,
    gemini_to_openai,
    openai_to_gemini,
    parse_model_with_method,
)
from app.streaming.openai_sse import parse_sse_json
from app.streaming.sse import create_sse_response, format_sse_event
from app.wire_json import dumps, loads

router = APIRouter(prefix="/v1beta/models", tags=["gemini"])


async def _gemini_stream(response: httpx.Response) -> AsyncGenerator[bytes]:
    try:
        async for event in parse_sse_json(response.aiter_raw()):
            if not isinstance(event, dict):
                continue
            typed_event = cast(dict[str, Any], event)
            choices = typed_event.get("choices", [])
            if not choices:
                continue
            choice = cast(dict[str, Any], choices[0])
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                delta = {}
            typed_delta = cast(dict[str, Any], delta)
            tool_calls = typed_delta.get("tool_calls", [])
            parts: list[dict[str, Any]] = []
            if typed_delta.get("content"):
                parts.append({"text": typed_delta["content"]})
            calls = cast(list[object], tool_calls) if isinstance(tool_calls, list) else []
            for call in calls:
                if not isinstance(call, dict):
                    continue
                typed_call = cast(dict[str, Any], call)
                function = typed_call.get("function", {})
                if isinstance(function, dict):
                    typed_function = cast(dict[str, Any], function)
                    arguments = typed_function.get("arguments", "{}")
                    parts.append(
                        {
                            "functionCall": {
                                "name": typed_function.get("name"),
                                "args": loads(
                                    arguments if isinstance(arguments, str) else "{}"
                                ),
                            }
                        }
                    )
            frame: dict[str, Any] = {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": parts,
                        },
                        "finishReason": choice.get("finish_reason"),
                        "index": 0,
                    }
                ]
            }
            yield format_sse_event(dumps(frame).decode())
    finally:
        await response.aclose()


@router.post("/{model_with_method}")
async def gemini_endpoint(
    model_with_method: str,
    body: dict[str, Any],
    client: OpenAIClientDependency,
    gate: ApprovalGateDependency,
) -> Response:
    try:
        model, method = parse_model_with_method(model_with_method)
    except GeminiPathError as error:
        return Response(
            content=dumps(
                {
                    "error": {
                        "code": 404,
                        "message": str(error),
                        "status": "NOT_FOUND",
                    }
                }
            ),
            status_code=404,
            media_type="application/json",
        )
    if method == "countTokens":
        count_request = CountTokensRequest.model_validate(body)
        contents = count_request.contents or (
            count_request.generate_content_request.contents
            if count_request.generate_content_request
            else []
        )
        text = "".join(
            part.text or ""
            for content in contents
            for part in content.parts
        )
        total = len(tiktoken.get_encoding("o200k_base").encode(text))
        return Response(
            content=dumps({"totalTokens": total}),
            media_type="application/json",
        )
    request_body = GenerateContentRequest.model_validate(body)
    stream = method == "streamGenerateContent"
    payload = ChatCompletionRequest.model_validate(
        gemini_to_openai(request_body, model=model, stream=stream)
    )
    guarded = await apply_approval_guard(
        payload.model_dump(mode="json", exclude_unset=True),
        model=model,
        endpoint=f"gemini-{method}",
        gate=gate,
    )
    payload = ChatCompletionRequest.model_validate(guarded)
    upstream = await client.chat(payload)
    if stream:
        if not upstream.is_success:
            try:
                error_body = loads(await upstream.aread())
            finally:
                await upstream.aclose()
            return Response(
                content=dumps(
                    {
                        "error": {
                            "code": upstream.status_code,
                            "message": str(error_body),
                            "status": "UPSTREAM_ERROR",
                        }
                    }
                ),
                status_code=upstream.status_code,
                media_type="application/json",
            )
        return create_sse_response(_gemini_stream(upstream))
    try:
        raw = loads(await upstream.aread())
        if not isinstance(raw, dict):
            raise ValueError("OpenAI response must be an object")
        return Response(
            content=dumps(openai_to_gemini(raw)),
            status_code=upstream.status_code,
            media_type="application/json",
        )
    finally:
        await upstream.aclose()