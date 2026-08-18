from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
from fastapi import APIRouter, Response

from app.deps import ApprovalGateDependency, OpenAIClientDependency, RuntimeDependency
from app.models.gemini import CountTokensRequest, GenerateContentRequest
from app.models.openai import ChatCompletionRequest
from app.pipeline.protocol_guard import apply_approval_guard
from app.protocols.gemini import (
    GeminiPathError,
    gemini_to_openai,
    openai_to_gemini,
    parse_model_with_method,
)
from app.routes.protocol_history import (
    finalize_protocol_history,
    history_stream,
    start_protocol_history,
)
from app.streaming.openai_sse import parse_sse_json
from app.streaming.sse import create_sse_response, format_sse_event
from app.tokenization.estimators import estimate_gemini_input
from app.wire_json import dumps, loads

router = APIRouter(prefix="/v1beta/models", tags=["gemini"])


async def _gemini_stream(response: httpx.Response) -> AsyncGenerator[bytes]:
    call_states: dict[int, dict[str, str]] = {}
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
            call_chunks = (
                cast(list[object], tool_calls)
                if isinstance(tool_calls, list)
                else []
            )
            for call in call_chunks:
                if not isinstance(call, dict):
                    continue
                typed_call = cast(dict[str, Any], call)
                index = int(typed_call.get("index", 0))
                function = typed_call.get("function", {})
                if isinstance(function, dict):
                    typed_function = cast(dict[str, Any], function)
                    state = call_states.setdefault(
                        index,
                        {"name": "", "arguments": ""},
                    )
                    if isinstance(typed_function.get("name"), str):
                        state["name"] = typed_function["name"]
                    if isinstance(typed_function.get("arguments"), str):
                        state["arguments"] += typed_function["arguments"]
            if choice.get("finish_reason") is not None:
                for state in call_states.values():
                    try:
                        args = loads(state["arguments"] or "{}")
                    except ValueError:
                        args = {"raw": state["arguments"]}
                    parts.append(
                        {
                            "functionCall": {
                                "name": state["name"],
                                "args": args,
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
    runtime: RuntimeDependency,
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
        total = estimate_gemini_input(count_request)
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
    history_entry = start_protocol_history(
        runtime,
        endpoint=f"gemini-{method}",
        model=model,
        payload=body,
    )
    upstream = await client.chat(payload)
    if stream:
        if not upstream.is_success:
            try:
                error_body = loads(await upstream.aread())
            finally:
                await upstream.aclose()
            await finalize_protocol_history(
                runtime,
                history_entry,
                status="failed",
            )
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
        return create_sse_response(
            history_stream(
                _gemini_stream(upstream),
                runtime=runtime,
                entry=history_entry,
            )
        )
    if not upstream.is_success:
        try:
            error_body = loads(await upstream.aread())
        finally:
            await upstream.aclose()
        await finalize_protocol_history(
            runtime,
            history_entry,
            status="failed",
        )
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
    try:
        raw = loads(await upstream.aread())
        if not isinstance(raw, dict):
            raise ValueError("OpenAI response must be an object")
        await finalize_protocol_history(
            runtime,
            history_entry,
            status="completed" if upstream.is_success else "failed",
        )
        return Response(
            content=dumps(openai_to_gemini(raw)),
            status_code=upstream.status_code,
            media_type="application/json",
        )
    finally:
        await upstream.aclose()
