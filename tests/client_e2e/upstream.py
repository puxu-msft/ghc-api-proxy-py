"""A stand-in for the Copilot upstream, scripted per test.

Every other test group in this repository drives the proxy from inside the process, which is the right trade for them: it is faster and it can assert on objects rather than bytes. This group exists for the one question those cannot answer — what the *real client* does with what we send it — and that question is only worth asking if everything between the client and the fake is real. So the proxy here is the actual application on an actual port, and only the far side is replaced.

The far side is replaced rather than recorded because these tests are about the client's behaviour, not upstream's. A cassette would pin both ends at once and make every test a re-run of one captured conversation; a script lets a test say "answer the first request with a tool call, the second with text" and then watch what the client does in between. Where upstream's exact behaviour is the subject, `tests/integration/recorded/` is the group that answers it.

Requests are kept in order and in full, so a test can assert on what the proxy actually sent — which is how the interesting failures show up. A client that never made the second request, or made it without the tool, looks identical from the outside to one that made it correctly.
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

BASE_URL = "https://copilot.example"

# Two models, because the routing decision under test depends on which endpoints a model
# advertises: a Claude model has only the Messages endpoint, and a GPT model has `/responses`,
# which is what makes one leg translate and the other not.
CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {
            "id": "claude-model",
            "capabilities": {"type": "chat", "supports": {"streaming": True, "tool_calls": True}},
            "supported_endpoints": ["/v1/messages"],
            "model_picker_enabled": True,
            "vendor": "Anthropic",
        },
        {
            "id": "gpt-model",
            "capabilities": {"type": "chat", "supports": {"streaming": True, "tool_calls": True}},
            "supported_endpoints": ["/responses"],
            "model_picker_enabled": True,
            "vendor": "OpenAI",
        },
    ],
}


@dataclass(slots=True)
class Exchange:
    """One request the proxy sent upstream, kept whole."""

    path: str
    body: dict[str, Any]

    @property
    def tools(self) -> list[dict[str, Any]]:
        raw = self.body.get("tools")
        if not isinstance(raw, list):
            return []
        return [cast(dict[str, Any], tool) for tool in cast(list[Any], raw) if isinstance(tool, dict)]

    @property
    def tool_types(self) -> list[str]:
        return [str(tool.get("type", "")) for tool in self.tools]


@dataclass(slots=True)
class ScriptedUpstream:
    """Answers in a fixed order, and remembers everything it was asked.

    A list rather than a mapping keyed on the request, because the sequence is the thing being
    tested: the second reply is only reached if the client did something with the first.
    """

    replies: list[Callable[[dict[str, Any]], httpx.Response]] = field(
        default_factory=lambda: list[Callable[[dict[str, Any]], httpx.Response]]()
    )
    seen: list[Exchange] = field(default_factory=lambda: list[Exchange]())
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "api.github.com" or path.endswith("/v2/token"):
            return httpx.Response(
                200, json={"token": "copilot", "expires_at": 5_000_000_000, "refresh_in": 1500}
            )
        if path.endswith("/models"):
            # Start-up, not the exchange under test, so it stays out of `seen`.
            return httpx.Response(200, json=CATALOG)

        body: dict[str, Any] = {}
        raw = request.content
        if raw:
            try:
                parsed: object = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                body = cast(dict[str, Any], parsed)

        with self._lock:
            self.seen.append(Exchange(path=path, body=body))
            index = len(self.seen) - 1
            reply = self.replies[index] if index < len(self.replies) else None
        if reply is None:
            # Loud rather than a default answer: a test that reaches an unscripted request has
            # discovered the client doing something it did not expect, and that is the finding.
            return httpx.Response(
                500,
                json={"error": {"message": f"no scripted reply for upstream request #{index + 1}"}},
            )
        return reply(body)


def anthropic_text(text: str, *, model: str = "claude-model") -> Callable[..., httpx.Response]:
    """A finished Anthropic reply carrying one text block."""

    def reply(body: dict[str, Any]) -> httpx.Response:
        if body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(
                    [
                        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
                        (
                            "content_block_delta",
                            {"index": 0, "delta": {"type": "text_delta", "text": text}},
                        ),
                        ("content_block_stop", {"index": 0}),
                    ],
                    model=model,
                    stop_reason="end_turn",
                ),
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_scripted",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    return reply


def anthropic_tool_call(
    name: str, tool_input: dict[str, Any], *, call_id: str = "toolu_scripted", model: str = "claude-model"
) -> Callable[..., httpx.Response]:
    """A reply asking the client to run one of its own tools.

    This is how a test gets the client to do something: the proxy cannot make Claude Code issue a
    web search, and neither can the test — only a reply that calls `WebSearch` can.
    """

    def reply(body: dict[str, Any]) -> httpx.Response:
        block = {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}
        if body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(
                    [
                        (
                            "content_block_start",
                            {"index": 0, "content_block": {**block, "input": {}}},
                        ),
                        (
                            "content_block_delta",
                            {
                                "index": 0,
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": json.dumps(tool_input),
                                },
                            },
                        ),
                        ("content_block_stop", {"index": 0}),
                    ],
                    model=model,
                    stop_reason="tool_use",
                ),
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_scripted",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [block],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    return reply


def _sse(
    blocks: list[tuple[str, dict[str, Any]]], *, model: str, stop_reason: str
) -> bytes:
    frames: list[str] = [
        _frame(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_scripted",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        )
    ]
    frames.extend(_frame(event, {"type": event, **data}) for event, data in blocks)
    frames.append(
        _frame(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        )
    )
    frames.append(_frame("message_stop", {"type": "message_stop"}))
    return "".join(frames).encode()


def _frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
