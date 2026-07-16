from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
from fastapi import APIRouter, Response

from app.deps import OpenAIClientDependency
from app.models.gemini import GenerateContentRequest
from app.models.openai import ChatCompletionRequest
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
            frame: dict[str, Any] = {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": typed_delta.get("content", "")}],
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
    body: GenerateContentRequest,
    client: OpenAIClientDependency,
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
    stream = method == "streamGenerateContent"
    payload = ChatCompletionRequest.model_validate(
        gemini_to_openai(body, model=model, stream=stream)
    )
    upstream = await client.chat(payload)
    if stream:
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