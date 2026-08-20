"""End-to-end over the new chain: HTTP in, upstream out, through a real ASGI app.

The upstream is a MockTransport under the real SDKs.
Upstream protocol behaviour is therefore the real thing rather than a friendlier stand-in.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import orjson
import pytest
import structlog
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import ValidationError
from starlette.requests import Request

from app.config.schema import ModelProviderConfig, ProxyConfig
from app.ghc_client import GhcApiClient, GhcClientConfig
from app.ghc_client.tokens import CopilotTokenManager
from app.model_provider import GithubCopilotProvider, ModelProvider
from app.observability import rejection_capture
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.logging import setup_logging
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.stream import stream_delivery
from app.server.composition import Chain, build_chain
from app.server.handler import delivery_buffer, stream_settings
from app.server.pipeline_app import (
    CHAIN_STATE_KEY,
    REQUEST_LOGGER,
    _AccountedStreamingResponse,  # pyright: ignore[reportPrivateUsage]
    _StreamAccounting,  # pyright: ignore[reportPrivateUsage]
    _Trace,  # pyright: ignore[reportPrivateUsage]
    _tracked_delivery,  # pyright: ignore[reportPrivateUsage]
    create_pipeline_app,
)
from app.streaming.idle_timeout import StreamIdleTimeoutError
from app.tokenization.state_store import TokenizationStateStore

BASE_URL = "https://copilot.example"

CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "claude-model", "supported_endpoints": ["/v1/messages"]},
        {"id": "gpt-model", "supported_endpoints": ["/responses"]},
        {"id": "embed-model", "supported_endpoints": ["/embeddings"]},
        {"id": "mute-model", "supported_endpoints": []},
    ],
}


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    disabled: list[str] | None = None,
) -> tuple[GithubCopilotProvider, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = CopilotTokenManager(StaticTokenSource(), http_client, clock=lambda: 1000)
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        tokens,
        GhcClientConfig(api_base_url_override=BASE_URL),
        interaction_id="interaction",
    )
    provider = GithubCopilotProvider(
        "ghc",
        client,
        ModelProviderConfig(type="github_copilot", disabled_models=disabled or []),
        http_client=http_client,
        base_url=BASE_URL,
    )
    provider.replace_catalog(CATALOG)
    return provider, http_client


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    mappings: dict[str, str] | None = None,
    tokenization_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> tuple[TestClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        if request.url.path.endswith("/models"):
            # The app refreshes the catalog before it accepts anything, so the stand-in has to
            # answer that too. Left out of `seen`: it is start-up, not the request under test.
            return httpx.Response(200, json=CATALOG)
        seen.append(request)
        return handler(request)

    provider, http_client = make_provider(recording)
    config = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot", "api_base_url": BASE_URL}},
            "default_model_provider": "ghc",
            "model_mappings": mappings or {},
            **(overrides or {}),
        }
    )
    providers: dict[str, ModelProvider] = {"ghc": provider}
    chain = build_chain(config, http_client=http_client, providers=providers)
    if tokenization_path is not None:
        # Otherwise the calibrator would read and write the real user data directory.
        chain = replace(chain, tokenization=TokenizationStateStore(tokenization_path))
    return TestClient(create_pipeline_app(chain)), seen


def test_anthropic_request_reaches_the_messages_endpoint_untranslated() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "content": []})
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "msg_1"
    assert str(seen[-1].url) == f"{BASE_URL}/v1/messages"


def test_anthropic_request_for_a_responses_model_is_translated() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": [{"type": "text", "text": "be brief"}],
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/responses"

    # The body upstream received must be Responses-shaped, not the Anthropic body we accepted.
    sent = seen[-1].read().decode()
    assert '"instructions"' in sent
    assert '"input"' in sent
    assert '"max_output_tokens"' in sent
    assert '"messages"' not in sent


def test_the_responses_leg_keeps_the_blank_blocks_it_was_given() -> None:
    """The primary path is not rewritten to satisfy a rule only the other path has.

    Measured on 2026-08-20 (`exp/260820-empty-text-probe/`): the live `/responses` answers 200 to an empty `input_text`, to a whitespace-only one, and to an assistant turn carrying an empty `output_text`, in the same run whose positive control got 400 from `/v1/messages` over the Anthropic spelling of the same thing. So removal belongs at `attempt.prepare` on the Anthropic leg, and nothing earlier.

    This is the guard against putting it back too early. A revision that strips before translation passes every unit test of the subscriber and fails here, which is the only place the difference shows.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": [
                {"type": "text", "text": "be brief"},
                {"type": "text", "text": "   \n"},
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "text", "text": "hi"},
                    ],
                }
            ],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    sent = orjson.loads(seen[-1].read())
    assert sent["instructions"] == "be brief\n\n   \n"
    assert sent["input"][0]["content"] == [
        {"type": "input_text", "text": ""},
        {"type": "input_text", "text": "hi"},
    ]


def test_an_anthropic_web_search_declaration_reaches_upstream_in_its_own_spelling() -> None:
    """The whole turn used to be rejected over it: `Invalid value: 'web_search_20250305'`, measured 2026-08-20 against gpt-5.6-sol. `{"type": "web_search"}` is answered 200 and the search really runs.

    Asserted on the bytes upstream received rather than on the translator's return value, because the declaration reached the wire through a shortcut that every unit test of the tool conversion walked straight past — `_function_tool` left alone anything without an `input_schema`, on the reasoning that it must already be Responses-shaped, and an Anthropic server tool has no `input_schema` either.

    The function tool beside it is the other half: translating the declaration must not disturb the client's real tools.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
            "tools": [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
                {"name": "get_time", "input_schema": {"type": "object"}},
            ],
        },
    )

    assert response.status_code == 200
    sent = orjson.loads(seen[-1].read())
    assert sent["tools"] == [
        {"type": "web_search"},
        {"type": "function", "name": "get_time", "parameters": {"type": "object"}},
    ]
    # The dated Anthropic spelling is the exact value upstream named when it refused the turn.
    assert b"web_search_20250305" not in seen[-1].read()


def test_a_streamed_search_is_delivered_as_a_line_rather_than_an_empty_block() -> None:
    """Driven by a real upstream recording: `tests/cassettes/responses_web_search_stream.json`.

    A `web_search_call` has no delta events and arrives with only an id, a status and a type on `output_item.added` — the query appears for the first time on `done`. Assembled the ordinary way, from the draft the `added` opened, it closed as an empty text block: the client got a blank content block ahead of every answer, and the one fact the item carried was thrown away.

    The cassette is used rather than a hand-written stream because that asymmetry is exactly the kind of thing a stand-in gets wrong — it would have been written from what the events are assumed to carry.
    """
    cassette = orjson.loads(Path("tests/cassettes/responses_web_search_stream.json").read_bytes())
    interaction = next(
        i for i in cassette["interactions"] if "responses" in i["request"]["path"]
    )
    sse = "".join(chunk["text"] for chunk in interaction["response"]["chunks"]).encode()

    client, _ = make_client(
        lambda _: httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "what day is it"}],
            "max_tokens": 256,
            "stream": True,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )

    assert response.status_code == 200
    deltas = [
        orjson.loads(line[6:])["delta"]["text"]
        for line in response.text.splitlines()
        if line.startswith("data: ") and '"content_block_delta"' in line
    ]
    assert deltas[0].startswith("[web_search] "), deltas
    assert "Thursday, August 20, 2026" in deltas[1]
    # No block may be delivered empty: that was the symptom, and it is invisible in a test that
    # only checks the answer arrived.
    assert all(text for text in deltas), deltas


def test_model_mapping_is_applied_before_the_upstream_call() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1"}),
        mappings={"opus": "claude-model"},
    )
    response = client.post("/v1/messages", json={"model": "opus", "messages": []})

    assert response.status_code == 200
    assert '"claude-model"' in seen[-1].read().decode()


def test_openai_group_is_served_under_every_compatible_prefix() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "resp_1"}))
    for prefix in ("", "/v1", "/openai/v1"):
        response = client.post(f"{prefix}/responses", json={"model": "gpt-model", "input": []})
        assert response.status_code == 200
    assert len(seen) == 3


def test_model_without_the_capability_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mute-model", "messages": []})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "CapabilityMissing"
    # Fail closed means nothing was sent, not that upstream rejected it.
    assert seen == []


def test_unknown_model_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mystery", "messages": []})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "UnknownModel"
    assert seen == []


def test_missing_model_is_rejected_by_inbound_parsing() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={}))
    response = client.post("/v1/messages", json={"messages": []})

    assert response.status_code == 400
    assert seen == []


def sse_upstream(*texts: str) -> bytes:
    """An upstream Anthropic SSE stream carrying one text block per argument."""
    frames: list[str] = []
    for index, text in enumerate(texts):
        for event, data in (
            ("content_block_start", {"index": index, "content_block": {"type": "text"}}),
            (
                "content_block_delta",
                {"index": index, "delta": {"type": "text_delta", "text": text}},
            ),
            ("content_block_stop", {"index": index}),
        ):
            frames.append(f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n")
    frames.append(
        'event: message_delta\ndata: {"delta":{"stop_reason":"end_turn"}}\n\n'
    )
    frames.append('event: message_stop\ndata: {}\n\n')
    return "".join(frames).encode()


def truncated_sse_upstream(*texts: str) -> bytes:
    """The same stream, cut off after the last block and before upstream said how it ended.

    Derived from `sse_upstream` by removing its ending rather than written out again, so a change to the frames upstream actually sends cannot leave this fixture describing a stream nobody produces.
    """
    whole = sse_upstream(*texts)
    ending = b'event: message_delta\ndata: {"delta":{"stop_reason":"end_turn"}}\n\n'
    assert ending in whole, "the fixture no longer ends the way this one is built from"
    return whole[: whole.index(ending)]


def sse_upstream_without_message_stop(*texts: str) -> bytes:
    """The same stream, cut after upstream said how the turn ended and before it closed the message.

    The other half of the Anthropic ending. Derived from `sse_upstream` for the same reason as `truncated_sse_upstream`.
    """
    whole = sse_upstream(*texts)
    ending = b"event: message_stop\ndata: {}\n\n"
    assert ending in whole, "the fixture no longer ends the way this one is built from"
    return whole[: whole.index(ending)]


def test_streaming_is_served_as_block_level_sse() -> None:
    # Each block is already whole before a frame is written; the SSE envelope carries them.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert events == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


def test_streamed_delta_carries_the_whole_block() -> None:
    # A delta holds a finished block, not a fragment of one.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("the whole thing"),
            headers={"content-type": "text/event-stream"},
        )
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )
    deltas = [
        orjson.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    text_deltas = [d["delta"]["text"] for d in deltas if d["type"] == "content_block_delta"]
    assert text_deltas == ["the whole thing"]


def test_upstream_error_status_reaches_the_client_as_a_gateway_failure() -> None:
    client, _ = make_client(lambda _: httpx.Response(500, json={"error": "upstream boom"}))
    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})
    assert response.status_code == 502


def test_unknown_path_is_not_served() -> None:
    client, _ = make_client(lambda _: httpx.Response(200, json={}))
    assert client.post("/nope", json={"model": "claude-model"}).status_code == 404


@pytest.mark.parametrize("path", ["/embeddings", "/v1/embeddings", "/openai/v1/embeddings"])
def test_embeddings_endpoint_is_served(path: str) -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"data": []}))
    response = client.post(path, json={"model": "embed-model", "input": "hi"})
    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/embeddings"


def test_translated_route_answers_in_the_format_the_client_asked_in() -> None:
    # The earlier translation test only checked the request. Half a crossing means the client
    # gets a Responses body it never asked for and cannot parse.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ],
            },
        )
    )
    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert body["content"] == [{"type": "text", "text": "hello"}]
    assert "output" not in body


def test_max_output_tokens_becomes_the_anthropic_stop_reason() -> None:
    # spec.md: an incomplete response due to the output-token limit is max_tokens downstream.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "cut"}],
                    }
                ],
            },
        )
    )
    response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.status_code == 200
    assert response.json()["stop_reason"] == "max_tokens"


def test_untranslated_route_body_is_returned_unchanged() -> None:
    client, _ = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "custom": {"kept": True}})
    )
    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})
    assert response.json()["custom"] == {"kept": True}


def test_upstream_429_is_seen_by_the_rate_limiter() -> None:
    # A 429 must reach the limiter, not merely surface as an error.
    from app.pipeline.rate_limiting import RateLimitMode

    provider, http_client = make_provider(
        lambda request: (
            httpx.Response(200, json={"token": "c", "expires_at": 5000, "refresh_in": 1500})
            if request.url.host == "api.github.com"
            else httpx.Response(429, json={"error": "slow down"})
        )
    )
    config = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot", "api_base_url": BASE_URL}},
            "default_model_provider": "ghc",
            "reactive_rate_limiter": {"retry_interval": 0, "request_interval": 0},
            "upstream_request_retry": {"max_total": 0},
        }
    )
    providers: dict[str, ModelProvider] = {"ghc": provider}
    chain = build_chain(config, http_client=http_client, providers=providers)
    client = TestClient(create_pipeline_app(chain))

    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert response.status_code == 502
    assert chain.rate_limiter_for("ghc").mode is RateLimitMode.LIMITED


def test_upstream_503_does_not_enter_limited_mode() -> None:
    # The spec keeps 503 out of the reactive triggers.
    from app.pipeline.rate_limiting import RateLimitMode

    provider, http_client = make_provider(
        lambda request: (
            httpx.Response(200, json={"token": "c", "expires_at": 5000, "refresh_in": 1500})
            if request.url.host == "api.github.com"
            else httpx.Response(503, json={"error": "unavailable"})
        )
    )
    config = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot", "api_base_url": BASE_URL}},
            "default_model_provider": "ghc",
            "upstream_request_retry": {"max_total": 0},
        }
    )
    providers: dict[str, ModelProvider] = {"ghc": provider}
    chain = build_chain(config, http_client=http_client, providers=providers)
    client = TestClient(create_pipeline_app(chain))

    client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert chain.rate_limiter_for("ghc").mode is RateLimitMode.NORMAL


def test_count_tokens_asks_upstream_and_returns_its_number() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 4242}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    # Upstream's own number, unmodified, and no claim that it was estimated.
    assert response.json() == {"input_tokens": 4242}
    assert str(seen[-1].url) == f"{BASE_URL}/v1/messages/count_tokens"


def test_count_tokens_falls_back_to_the_local_estimate() -> None:
    """A provider that fails hands over to the next, so a broken upstream degrades rather than 502s.

    The reply says `estimated`, because an estimate presented as a measurement is worse than no
    answer: the caller sizes its request against it.
    """
    client, _ = make_client(lambda _: httpx.Response(500, json={"error": "upstream is down"}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hello there"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["estimated"] is True
    assert body["input_tokens"] > 0


def test_count_tokens_asks_about_the_mapped_model() -> None:
    # A count that ignored model_mappings would answer about a model the request never reaches.
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"input_tokens": 7}),
        mappings={"alias": "claude-model"},
    )
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "alias", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert orjson.loads(seen[-1].read())["model"] == "claude-model"


def test_count_tokens_accepts_a_body_without_max_tokens() -> None:
    """Anthropic's own count_tokens does not require it; requiring it would reject valid bodies.

    The default supplied to make the body countable must stay on this side of the wire. Asserting
    only that the request succeeds cannot tell the two apart — a version that mutated the outbound
    payload passes that just as well.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 11}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["input_tokens"] == 11
    assert "max_tokens" not in orjson.loads(seen[-1].read())


def test_count_tokens_estimates_locally_for_a_model_with_no_upstream_counter() -> None:
    """The gap between refusal and failure, corrected 2026-08-20.

    This asserted 400 on the reasoning that answering would give "a count for a model this request can never reach". That premise is false, and demonstrably so in this same file: `test_anthropic_request_for_a_responses_model_is_translated` sends `gpt-model` a Messages body to `/v1/messages` and gets 200 — the difference between the two URLs is the whole argument, since it is the same model and the same inbound protocol. The model is reached; it is reached by translation. What `gpt-model` lacks is not reachability but a *counter* — upstream's only one serves the Anthropic protocol, and the OpenAI family reports usage on a finished response instead.

    So a 400 here told a client that a request it was about to make successfully could not be measured. The route now decides whether an upstream counter exists before one is called, and the answer falls to the local estimate, marked `estimated`.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 99}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "gpt-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["estimated"] is True
    assert body["input_tokens"] > 0
    # Never asked: a refusal from this counter is fatal, so it must not be tried and caught.
    assert seen == []


def test_count_tokens_rejects_a_body_that_is_not_countable() -> None:
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 1}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": "not a list of messages"},
    )

    assert response.status_code == 400
    assert seen == [], "an uncountable body must not reach upstream"


def test_count_tokens_refuses_a_model_without_the_messages_capability() -> None:
    """Refused by routing, before any counter is chosen.

    The refusal here comes from `decide_route`, not from the provider's own gate — a mutation that
    removes the provider check leaves this test green. The provider gate has its own test in
    `tests/unit/test_model_provider.py`.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 1}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "mute-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400
    assert seen == []


def test_what_the_calibrator_learns_survives_a_restart(tmp_path: Path) -> None:
    """Learning that dies with the process makes `local` worse the more the service restarts.

    Two apps over the same state file. The first is taught by a real upstream count; the second
    never reaches upstream at all, so the number it returns can only have come from disk.
    """
    state = tmp_path / "tokenization.json"
    body = {"model": "claude-model", "messages": [{"role": "user", "content": "hello there"}]}

    untaught, _ = make_client(
        lambda _: httpx.Response(503, json={"error": "down"}),
        tokenization_path=tmp_path / "empty.json",
    )
    with untaught:
        before = untaught.post("/v1/messages/count_tokens", json=body).json()["input_tokens"]

    teacher, _ = make_client(
        lambda _: httpx.Response(200, json={"input_tokens": before * 10}),
        tokenization_path=state,
    )
    with teacher:
        assert teacher.post("/v1/messages/count_tokens", json=body).status_code == 200
    assert state.is_file(), "the lifespan must flush what was learnt"

    successor, seen = make_client(
        lambda _: httpx.Response(503, json={"error": "down"}),
        tokenization_path=state,
    )
    with successor:
        after = successor.post("/v1/messages/count_tokens", json=body).json()
    assert after["estimated"] is True
    assert after["input_tokens"] != before, "the successor did not read what was learnt"
    assert seen, "this test is only meaningful if upstream really was tried and failed"


def test_a_refused_body_is_kept_where_someone_can_read_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the note is written on the path a request actually takes, not merely that a function can write one.

    Two investigations in one day had to reconstruct the outbound request from the client's own transcripts, because nothing here kept it. A capture module nobody calls looks identical to a working one from every other angle — which is the failure this repository has already had three times — so this asserts through the app, and on the body as it went out rather than as it arrived.
    """
    monkeypatch.setattr(rejection_capture, "user_data_path", lambda: tmp_path)
    refusal = '{"type":"error","error":{"message":"messages: text content blocks must be non-empty"}}'
    client, seen = make_client(lambda _: httpx.Response(400, text=refusal))

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-model",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "text", "text": ""}]}
            ],
        },
    )

    assert response.status_code == 400
    captures = list((tmp_path / "rejected").glob("*.json"))
    assert len(captures) == 1, f"nothing kept the refused body: {captures}"
    record = orjson.loads(captures[0].read_bytes())
    assert record["status"] == 400
    assert "text content blocks must be non-empty" in record["upstream"]
    # The blank block is gone from what was sent, so the capture must show it gone too: this is the body upstream refused, not the one the client offered.
    assert record["payload"]["messages"][0]["content"] == [{"type": "text", "text": "hi"}]
    assert record["payload"] == orjson.loads(seen[-1].read())


def thinking(text: str = "t", signature: str = "sig") -> dict[str, Any]:
    return {"type": "thinking", "thinking": text, "signature": signature}


def test_adjacent_thinking_blocks_are_separated_before_they_reach_upstream() -> None:
    """Upstream rejects adjacent thinking blocks with a 400 the client cannot act on.

    Asserted against the body that actually went out rather than against the fixup in isolation:
    the fixup has to run *before* translation, and a test of the function alone cannot tell whether
    the wiring put it there or after.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-model",
            "messages": [
                {"role": "assistant", "content": [thinking("a"), thinking("b")]},
                {"role": "user", "content": "go on"},
            ],
        },
    )

    assert response.status_code == 200
    sent = orjson.loads(seen[-1].read())
    blocks = sent["messages"][0]["content"]
    kinds = [block["type"] for block in blocks]
    assert kinds != ["thinking", "thinking"], "adjacent thinking blocks reached upstream"
    assert kinds[0] == "thinking" and kinds[-1] == "thinking"
    assert len(kinds) == 3, "a separator should sit between them"


def test_a_thinking_block_with_nothing_in_it_is_dropped() -> None:
    # Neither signature nor text: it carries nothing upstream can use, and it would otherwise be
    # spent as a separator between two real ones.
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-model",
            "messages": [
                {
                    "role": "assistant",
                    "content": [thinking("keep"), thinking(text="", signature="")],
                },
            ],
        },
    )

    assert response.status_code == 200
    blocks = orjson.loads(seen[-1].read())["messages"][0]["content"]
    assert [block["type"] for block in blocks] == ["thinking"]
    assert blocks[0]["thinking"] == "keep"


def test_a_user_turn_is_left_alone() -> None:
    """The negative control: the adjacency rule the spec states is about *assistant* turns.

    Uses adjacent thinking blocks rather than text ones on purpose. `destack_content` is a no-op
    on content with no adjacent thinking blocks, so a user turn carrying two text blocks passes
    this test whether the role is checked or not — it cannot tell the guard from its absence.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    original = [thinking("one"), thinking("two")]
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": original}]},
    )

    assert response.status_code == 200
    assert orjson.loads(seen[-1].read())["messages"][0]["content"] == original


def layout(value: object) -> dict[str, Any]:
    return {"hook_fix_anthropic_request": {"thinking": {"assistant_message_layout": value}}}


def assistant_blocks(seen: list[httpx.Request]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], orjson.loads(seen[-1].read())["messages"][0]["content"])


def send_stacked(client: TestClient) -> httpx.Response:
    """Two adjacent thinking blocks with a real text block after them.

    The real block is what tells the two layouts apart: `move_and_synthetic` moves it between the
    thinking blocks, `synthetic_only` leaves it where it is and inserts a marker. Without it both
    layouts produce the same three blocks and no test can distinguish them.
    """
    return client.post(
        "/v1/messages",
        json={
            "model": "claude-model",
            "messages": [
                {
                    "role": "assistant",
                    "content": [thinking("a"), thinking("b"), {"type": "text", "text": "real"}],
                }
            ],
        },
    )


def test_move_and_synthetic_separates_with_the_real_block() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}),
        overrides=layout("move_and_synthetic"),
    )
    assert send_stacked(client).status_code == 200

    blocks = assistant_blocks(seen)
    assert [block["type"] for block in blocks] == ["thinking", "text", "thinking"]
    # The real block became the separator rather than a synthetic marker being inserted.
    assert blocks[1]["text"] == "real"


def test_synthetic_only_leaves_the_real_block_where_it_was() -> None:
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}),
        overrides=layout("synthetic_only"),
    )
    assert send_stacked(client).status_code == 200

    blocks = assistant_blocks(seen)
    assert [block["type"] for block in blocks] == ["thinking", "text", "thinking", "text"]
    assert blocks[1]["text"] != "real", "synthetic_only must not move the real block"
    assert blocks[3]["text"] == "real"


def test_layout_false_passes_the_stack_through_untouched() -> None:
    # The opt-out: an operator who turns it off gets exactly what the client sent.
    client, seen = make_client(
        lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}),
        overrides=layout(False),
    )
    assert send_stacked(client).status_code == 200
    assert [block["type"] for block in assistant_blocks(seen)] == ["thinking", "thinking", "text"]


def test_an_undefined_layout_value_is_refused() -> None:
    # `true` is not one of the three spellings the spec defines; accepting it would silently
    # rewrite request bodies under a config the operator got wrong.
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(layout(True))


def sse_thinking_upstream(signature: str) -> bytes:
    """Upstream's thinking frame: the signature rides in content_block_start, never as a delta."""
    frames: list[tuple[str, dict[str, Any]]] = [
        (
            "content_block_start",
            {
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": signature},
            },
        ),
        (
            "content_block_delta",
            {"index": 0, "delta": {"type": "thinking_delta", "thinking": "pondering"}},
        ),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}}),
        ("message_stop", {}),
    ]
    return "".join(
        f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n" for event, data in frames
    ).encode()


def stream_thinking(client: TestClient) -> httpx.Response:
    return client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )


def signature_compat(value: object) -> dict[str, Any]:
    return {"hook_fix_anthropic_sse": {"thinking": {"content_block_start_compat": value}}}


def test_the_signature_shim_is_driven_by_configuration() -> None:
    """Turning it off in the config must reach the frames the client receives.

    The shim's default matches `StreamSettings`' default, so a test that never sets a non-default
    value passes whether the config is read or ignored — which is exactly the wiring under test.
    """
    def upstream(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=sse_thinking_upstream("sig-abc"),
            headers={"content-type": "text/event-stream"},
        )

    on, _ = make_client(upstream)
    assert "signature_delta" in stream_thinking(on).text

    off, _ = make_client(upstream, overrides=signature_compat(False))
    assert "signature_delta" not in stream_thinking(off).text


def _chain_of(client: TestClient) -> Chain:
    """The chain the app was built with.

    Reached through `app.state` rather than returned by `make_client`, so the existing helper's signature stays as every other test in this file uses it. The cast is needed because `TestClient.app` is typed as a bare ASGI callable.
    """
    return cast(Chain, getattr(cast(FastAPI, client.app).state, CHAIN_STATE_KEY))


def _registry(client: TestClient) -> ActiveRequestRegistry:
    return _chain_of(client).active_requests


def test_a_request_is_in_the_footer_registry_while_it_is_in_flight() -> None:
    # Observed from inside the upstream handler, the one point that runs while the request genuinely is in flight. Asserting after the response returns could only ever see an empty registry, and would pass just as happily if nothing were ever registered.
    inflight: list[str] = []

    def upstream(_: httpx.Request) -> httpx.Response:
        inflight.extend(entry.model for entry in _registry(client).snapshot())
        return httpx.Response(200, json={"id": "msg_1", "content": []})

    client, _ = make_client(upstream)
    client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    # Resolved by the time upstream is called, because routing decides it before the call and says so immediately. This asserted `[""]` while the model was published only after the whole exchange finished, which meant the footer read `(resolving)` for the entire upstream call — not slow feedback but wrong feedback, and the test was encoding it as correct.
    assert inflight == ["claude-model"]
    # Released afterwards, or the footer fills with requests that finished long ago.
    assert _registry(client).snapshot() == []


def test_a_streaming_request_stays_registered_until_its_body_is_finished() -> None:
    """The seam this design is most likely to get wrong.

    A streaming request has produced nothing when its handler returns — the body is consumed after. Releasing at the handler's exit would drop it off the footer at the moment it starts streaming, which is exactly when it is worth watching.

    Asserted on the order of the registry's own calls rather than by snapshotting from the client side. `TestClient` drives the ASGI app to completion before handing back a response, so a client-side snapshot finds an empty registry whether the release is correctly placed or not — it cannot tell the two apart, which is the one thing this test exists to do.
    """
    calls: list[str] = []

    class Recording(ActiveRequestRegistry):
        def add(self, request_id: str, *, model: str = "", started_at: float | None = None) -> None:
            calls.append("add")
            super().add(request_id, model=model, started_at=started_at)

        def add_bytes(self, request_id: str, count: int) -> None:
            calls.append("bytes")
            super().add_bytes(request_id, count)

        def remove(self, request_id: str) -> None:
            calls.append("remove")
            super().remove(request_id)

    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )
    chain = _chain_of(client)
    setattr(cast(FastAPI, client.app).state, CHAIN_STATE_KEY, replace(chain, active_requests=Recording()))

    response = client.post(
        "/v1/messages", json={"model": "claude-model", "messages": [], "stream": True}
    )
    assert response.status_code == 200

    assert calls[0] == "add"
    assert "bytes" in calls, "no downstream bytes were counted, so the footer could never show one"
    # The decisive assertion: every byte is counted before the slot is released. Releasing at the handler's exit puts `remove` ahead of them all.
    assert calls.index("remove") > max(index for index, call in enumerate(calls) if call == "bytes")
    assert _registry(client).snapshot() == []


def test_a_client_that_stops_reading_still_releases_its_slot() -> None:
    # The release sits in a `finally` rather than after the loop: a request that only leaves the footer on the happy path leaves it stale exactly when something has gone wrong.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )

    with client.stream(
        "POST", "/v1/messages", json={"model": "claude-model", "messages": [], "stream": True}
    ) as response:
        next(response.iter_bytes())

    assert _registry(client).snapshot() == []


@pytest.fixture
def request_log() -> Iterator[None]:
    """Install the real logging configuration for the duration of one test.

    Needed rather than incidental: unconfigured, structlog writes through its own `PrintLogger` straight to stdout and never creates a `LogRecord`, so `caplog` sees nothing and every assertion below passes on an empty list. Calling the production setup is also what makes these tests exercise the wiring the CLI installs, instead of a second arrangement that only exists here.
    """
    setup_logging(log_format="text", colors=False)
    try:
        yield
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()


def _request_lines(records: list[logging.LogRecord]) -> list[str]:
    """The completion lines `_serve` wrote, in order.

    Selected by logger name, not by message content. Content matching looked equivalent until it also picked up `httpx`, which narrates every upstream call with the same route in it — and silently turned "exactly one line" into "exactly two".

    The message is pulled out of the structlog event dict rather than from `getMessage()`: with `ProcessorFormatter` the record carries the dict and the rendering happens at the handler, so `getMessage()` returns the whole dict stringified.
    """
    lines: list[str] = []
    for record in records:
        if record.name != REQUEST_LOGGER or record.levelno < logging.INFO:
            continue
        payload = record.msg
        if isinstance(payload, dict):
            lines.append(str(cast(dict[str, Any], payload)["event"]))
        else:
            lines.append(record.getMessage())
    return lines


def _request_outcomes(records: list[logging.LogRecord]) -> list[tuple[str, str]]:
    """Each completion line paired with the `ok` / `fail` the prefix processor renders from it.

    Separate from `_request_lines` because the two halves are decided in different places and can disagree — the fields come from what the reply carried, the prefix comes from `status_for` — and reading only the message cannot see a request reported as clean when it was not. That is exactly the shape the truncation bug had.
    """
    outcomes: list[tuple[str, str]] = []
    for record in records:
        if record.name != REQUEST_LOGGER or record.levelno < logging.INFO:
            continue
        payload = record.msg
        assert isinstance(payload, dict), "the completion line is expected to arrive as a structlog event dict"
        event = cast(dict[str, Any], payload)
        outcomes.append((str(event["event"]), str(event["status"])))
    return outcomes


def _request_prefixes(records: list[logging.LogRecord]) -> list[str]:
    """The fixed-width prefix each completion line was actually rendered with.

    Worth asserting separately from the status word it comes from: `_add_status_prefix` falls back to `[....]` for a status it does not recognise, so a status the prefix table has never heard of produces a line that looks merely unremarkable rather than one that fails.
    """
    return [
        str(cast(dict[str, Any], record.msg)["prefix"])
        for record in records
        if record.name == REQUEST_LOGGER and record.levelno >= logging.INFO
    ]


def test_a_request_still_arriving_is_already_in_the_footer(request_log: None) -> None:
    """The invariant behind the reported blank footer.

    Registration used to happen after the body was read, so a client that announced a body and stopped sending did not exist as far as the display was concerned — the shutdown waited on it correctly and nothing said so. Asserted from inside `body()` because that is the window: any check after `_serve` returns sees an empty registry whether the fix is present or not.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    seen_while_reading: list[list[str]] = []

    class Watching(ActiveRequestRegistry):
        pass

    watching = Watching()
    setattr(cast(FastAPI, client.app).state, CHAIN_STATE_KEY, replace(chain, active_requests=watching))

    original = Request.body

    async def body(self: Request) -> bytes:
        seen_while_reading.append([entry.request_id for entry in watching.snapshot()])
        return await original(self)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Request, "body", body)
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    assert seen_while_reading and seen_while_reading[0], "the request was invisible while its body was still arriving"
    assert watching.snapshot() == [], "and it must still be released when the request ends"


def test_a_served_request_writes_exactly_one_log_line(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The gap that let a silent server ship.

    Every part of the footer was tested and correct while the log stream it sits under did not exist: nothing in the served chain emitted a line, and nothing asserted that anything did. A component test cannot catch that — only one that watches the served path can.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # A success names the model instead of the route, and carries the status and how long it took.
    assert lines[0].startswith("H1/H1 200 anthropic-messages/claude-model ")


def test_a_refused_request_is_reported_with_its_route_and_reason(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "no-such-model", "messages": []})

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # A failure keeps `METHOD /path`, because that is what has to be reproduced, and ends in the reason. One protocol label rather than a pair: this request never reached upstream, so there is no second leg to name.
    assert lines[0].startswith("H1 400 POST /v1/messages ")
    assert "no-such-model" in lines[0]


def test_a_streaming_request_reports_what_it_actually_delivered(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    # Written by the delivery generator, not by the handler: at the moment the handler returns a stream has sent nothing, so a line written there would report every stream as having delivered zero bytes.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": [], "stream": True})

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    assert lines[0].startswith("H1/H1 200 anthropic-messages/claude-model ")
    assert "↓" in lines[0], "a delivered stream must report its byte count"
    assert "↓0B" not in lines[0]


def test_a_stream_that_never_terminated_is_not_reported_as_a_clean_finish(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The reported line, in full: `[ OK ] 09:00:11 H1/H2 200 anthropic-messages/claude-opus-5 385.0s ↑583.5KB ↓43.2KB`.

    43KB had come back over 385 seconds and then upstream stopped without saying how the turn ended. The reply summary was gated on having seen that ending, so it was never taken onto the line — and every field that says what a reply *was* dropped out together, leaving something indistinguishable from a quiet successful request. The status could not correct it either: it is fixed when the response headers arrive and stays 200 however the stream ends.

    So the two halves are asserted separately. The prefix must say `fail`, and the line must name the truncation rather than leave it to be inferred from which fields are missing — an absence reads the same as a field this endpoint does not report.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=truncated_sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": [], "stream": True})

    (line, status), = _request_outcomes(caplog.records)
    assert status == "fail", f"a truncated stream was reported as a clean finish: {line}"
    assert "upstream stream ended without a terminal event" in line
    # The reason upstream never gave must not appear on the line under any spelling. `end_turn` is the one the code had to invent for the client's benefit; the operator is told what actually happened.
    assert "end_turn" not in line


async def test_an_upstream_that_tore_says_so_and_says_what_broke(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The third ending, which the first version of this fix filed under the second.

    A reset, a `ReadError`, a converter blowing up — upstream failing mid-stream leaves the delivery generator by *raising*, not by being closed, so it skips the flag that marks a drained stream and used to be reported as a client that walked away. Two different sides of the proxy, one message.

    The error text is on the line because nothing else on this path writes it down: it unwinds out through the framework, and the request's own line is the only record that survives. A line saying merely that the stream stopped throws away the one fact worth having.

    This and the disconnect test below reach past the HTTP layer this file is otherwise about, because neither ending can be produced through it — `TestClient` drains the body rather than disconnecting, and no upstream stand-in reachable from a request can tear mid-stream. They stay here rather than moving to a component file because they need this file's `make_client` and `_chain_of` to build a real chain, and duplicating that to satisfy the directory name would be the worse trade.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = _Trace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain, request_id="req_1", trace=trace, status_code=200, assembler=assembler
    )
    chain.active_requests.add("req_1")

    async def tears_after_the_first_block() -> AsyncIterator[bytes]:
        whole = sse_upstream("first", "second")
        yield whole[: whole.index(b'event: content_block_start\ndata: {"index":1', 1)]
        raise httpx.ReadError("connection reset by peer")

    delivery = _tracked_delivery(
        stream_delivery(
            tears_after_the_first_block(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            message_id="msg_1",
            model="claude-model",
        ),
        accounting,
    )

    with caplog.at_level(logging.INFO):
        async with asyncio.timeout(10):
            assert await anext(delivery), "the first block should have reached the client"
            with pytest.raises(httpx.ReadError):
                async for _ in delivery:
                    pass

    (line, status), = _request_outcomes(caplog.records)
    assert status == "fail"
    assert "connection reset by peer" in line, f"the only record of what broke was dropped: {line}"
    # Neither of the other two endings: upstream did not run out, and nobody on this side walked away.
    assert "upstream stream ended without a terminal event" not in line
    assert "delivery stopped before upstream finished" not in line


async def test_a_tear_after_the_stop_reason_is_still_a_tear(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The hole the previous shape of this gate left, and the reason it needs two conditions.

    `stream_delivery` writes its terminal frames *after* its event loop, so a tear unwinds straight past them: the client gets neither `message_delta` nor `message_stop` even though the assembler recorded upstream's. Gating the report on upstream's stop reason alone therefore let this land as a green line reading `end_turn` and nothing else — the exact silence this whole change exists to remove, restored on a narrower path.

    The other tear test cannot catch it: that one breaks after the first block, so no reason was ever recorded and the gate is never reached.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = _Trace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain, request_id="req_1", trace=trace, status_code=200, assembler=assembler
    )
    chain.active_requests.add("req_1")

    async def tears_after_its_stop_reason() -> AsyncIterator[bytes]:
        # Everything including `message_delta`, so upstream's reason is on the record, and then nothing.
        yield sse_upstream_without_message_stop("first", "second")
        raise httpx.ReadError("connection reset by peer")

    delivery = _tracked_delivery(
        stream_delivery(
            tears_after_its_stop_reason(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            message_id="msg_1",
            model="claude-model",
        ),
        accounting,
    )

    with caplog.at_level(logging.INFO):
        async with asyncio.timeout(10):
            with pytest.raises(httpx.ReadError):
                async for _ in delivery:
                    pass

    assert assembler.terminal.stop_reason == "end_turn", "upstream did give its reason before it tore"
    (line, status), = _request_outcomes(caplog.records)
    assert status == "fail", f"a tear was reported as a clean finish: {line}"
    assert "connection reset by peer" in line


def test_a_stream_cut_after_its_stop_reason_is_not_called_truncated(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """An Anthropic upstream splits the ending in two, and only the second half is optional.

    `message_delta` carries the stop reason and the usage; `message_stop` merely closes. A stream cut between them has told us everything the client is owed and loses nothing downstream — the terminal frames go out with upstream's own reason, not a synthesised one.

    Reported as truncated anyway, the line argued with itself: `end_turn` followed immediately by a note saying nothing ended. So the report is gated on whether a reason came back rather than on the closing frame, which is also why this cannot be folded into the truncation test above — on the Responses leg the two arrive together and the distinction is invisible.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream_without_message_stop("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": [], "stream": True})

    (line, status), = _request_outcomes(caplog.records)
    assert status == "ok", f"upstream gave its reason, so nothing here is a failure: {line}"
    assert "end_turn" in line
    assert "upstream stream ended without a terminal event" not in line


async def test_a_client_that_walked_away_is_not_blamed_on_upstream(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The other way a stream reaches its end with no terminal event seen.

    `finish` runs from a `finally`, so a client that stops reading lands in exactly the same place as a truncated upstream: nothing was assembled to the end, `seen` is false. But upstream was fine — it was still sending — and reporting this as an upstream truncation points the operator at the wrong side of the proxy, which is worse than the silence it replaced.

    Driven through `_tracked_delivery` rather than `TestClient`, which cannot express this. Written the obvious way first — stream over HTTP, stop reading, assert — it passed while proving nothing: `TestClient` drains the response body on the way out, so upstream finished, the line said `end_turn`, and no disconnect was ever exercised. Closing the delivery generator is what a client going away does to this code, and it is reachable only from here.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = _Trace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain, request_id="req_1", trace=trace, status_code=200, assembler=assembler
    )
    chain.active_requests.add("req_1")

    async def still_sending() -> AsyncIterator[bytes]:
        whole = sse_upstream("first", "second")
        cut = whole.index(b'event: content_block_start\ndata: {"index":1', 1)
        yield whole[:cut]
        # Upstream has more to send and no idea anyone left. Cancelled when the delivery generator is closed.
        await asyncio.Event().wait()

    delivery = _tracked_delivery(
        stream_delivery(
            still_sending(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            message_id="msg_1",
            model="claude-model",
        ),
        accounting,
    )

    with caplog.at_level(logging.INFO):
        async with asyncio.timeout(10):
            assert await anext(delivery), "the first block should have reached the client"
            # And now the client is gone.
            await delivery.aclose()

    (line, status), = _request_outcomes(caplog.records)
    # `gone`, not `fail`: nothing here is the proxy's fault or upstream's, and painting every cancelled turn the same red as a reset would bury the resets. Ruled 2026-08-20.
    assert status == "gone", f"a client that walked away is not a failure: {line}"
    assert _request_prefixes(caplog.records) == ["[GONE]"], "the status word never reached a prefix the reader sees"
    assert "upstream stream ended without a terminal event" not in line, (
        f"a client-side disconnect was reported as an upstream fault: {line}"
    )
    assert "delivery stopped before upstream finished" in line


def test_a_stream_that_did_terminate_is_still_reported_as_one(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The control for the test above, on the same fixture minus the cut.

    Without it, reporting *every* stream as truncated would pass — and the fields the fix restores are exactly the ones a clean stream has always carried, so nothing else would notice.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=sse_upstream("first", "second"),
            headers={"content-type": "text/event-stream"},
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": [], "stream": True})

    (line, status), = _request_outcomes(caplog.records)
    assert status == "ok"
    assert "end_turn" in line
    assert "upstream stream ended without a terminal event" not in line


def test_a_request_that_reached_upstream_reports_bytes_in_both_directions(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The line describes the proxy's exchange with upstream, so both directions are upstream's.

    `↑` is what went out on the wire to upstream — not the client's body, which translation rewrites — and `↓` is what came back. A request refused before it ever reached upstream therefore reports neither: it has no upstream exchange to describe, and printing the client-side sizes there would be inventing numbers about a conversation that never happened.
    """
    client, _ = make_client(lambda _: httpx.Response(200, json={"id": "msg_1", "content": []}))

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})
        client.post("/v1/messages", json={"model": "no-such-model", "messages": []})

    answered, refused = _request_lines(caplog.records)
    assert "↑" in answered and "↓" in answered
    assert "↑" not in refused and "↓" not in refused


def test_the_count_endpoint_reports_its_model_and_its_number(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """A count is a model request: it resolves a model and produces a token number.

    Its line reported neither, which made the endpoint most likely to be called in a loop the least legible one on the proxy. Routing happens inside the handler, so both facts only exist once it has returned.
    """
    client, _ = make_client(
        lambda _: httpx.Response(200, json={"input_tokens": 4242}), mappings={"alias": "claude-model"}
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages/count_tokens", json={"model": "alias", "messages": [{"role": "user", "content": "hi"}]})

    line = _request_lines(caplog.records)[0]
    assert "alias → claude-model" in line
    assert "↑4.2k" in line


def test_upstream_token_usage_reaches_the_line(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    # Taken from the payload that goes downstream, so the numbers on the line are the ones the client was told.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 456, "cache_read_input_tokens": 8000},
            },
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    line = _request_lines(caplog.records)[0]
    assert "↑12+8.0k" in line
    assert "↓456" in line
    assert line.endswith("end_turn")


def test_a_responses_upstream_is_logged_in_its_own_words(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The line reports the upstream exchange, so it uses the upstream's names.

    A buffered reply is read back *after* translation, by which point it is Anthropic-shaped whatever answered it — so nothing in the body still says a Responses API was on the other end. The route does, and that is where the wording comes from. Worth an end-to-end assertion rather than a unit one: every piece of this was already correct in isolation while the buffered path was the one deriving its own answer.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "completed",
                "output": [
                    {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "sealed"},
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "Bash", "arguments": "{}"},
                ],
            },
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    line = _request_lines(caplog.records)[0]
    # `reason`, not `think`: the Responses API sends reasoning items, and which upstream a turn went to is exactly what somebody reads this log to find out.
    assert "reason(enc:1)" in line
    # `function_call`, not the `tool_use` stop reason synthesised downstream for the client's benefit — a Responses trace contains no `tool_use` to go looking for.
    assert "function_call(Bash)" in line
    assert "think(" not in line and "tool_use(" not in line


def responses_sse_upstream(usage: dict[str, Any] | None = None) -> bytes:
    """A Responses SSE stream carrying one sealed reasoning item and one function call.

    Hand-written because what it has to hold up is the route → assembler → line wiring under an event contract that is already known, not how Copilot actually behaves on the wire. The frames only have to be shaped enough for the assembler to open and close both items. Anything asserting the real upstream's quirks — id instability, chunk boundaries — belongs on a cassette instead; see `tests/integration/recorded/`.
    """
    items: list[dict[str, Any]] = [
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "sealed"},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "Bash", "arguments": ""},
    ]
    frames: list[str] = []
    for index, item in enumerate(items):
        data: dict[str, Any] = {"output_index": index, "item": item}
        for event in ("response.output_item.added", "response.output_item.done"):
            frames.append(f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n")
    reported = usage if usage is not None else {"input_tokens": 3, "output_tokens": 4}
    frames.append(
        "event: response.completed\n"
        f'data: {orjson.dumps({"response": {"usage": reported}}).decode()}\n\n'
    )
    return "".join(frames).encode()


def test_a_streamed_responses_reply_is_logged_in_its_own_words(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The streaming half of the same wording decision.

    Its dialect comes from the assembler that read the stream rather than from the route, so the two paths reach the same answer by different routes and both have to be held to it.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200, content=responses_sse_upstream(), headers={"content-type": "text/event-stream"}
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "gpt-model", "messages": [], "stream": True})

    line = _request_lines(caplog.records)[0]
    assert "reason(enc:1)" in line
    assert "function_call(Bash)" in line
    assert "think(" not in line and "tool_use(" not in line


def test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """An inbound `/responses` reply keeps its own shape end to end, and the Anthropic reader finds nothing in it.

    The regression this pins: summarising through a record whose stop reason defaults to `end_turn` turned "nobody said" into "finished cleanly", so every one of these lines claimed an outcome no upstream had reported. An absent `content` is indistinguishable from a reply that had none, which is exactly why the empty summary has to be refused rather than absorbed.

    Reporting nothing here is the honest state and also the pre-existing one; giving these routes a real summary is open work, tracked in `.dev/docs/tui/deferred.md`.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "completed",
                "output": [
                    {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "sealed"},
                    {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "Bash", "arguments": "{}"},
                ],
            },
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/responses", json={"model": "gpt-model", "input": []})

    line = _request_lines(caplog.records)[0]
    assert line.startswith("H1/H1 200 openai-responses/gpt-model ")
    assert "end_turn" not in line, "a stop reason nobody sent must not appear"
    # The reply's contents are simply not reported on this route yet. Asserted so that giving it a reader is a deliberate change to this test rather than a silent one.
    assert "reason(" not in line and "think(" not in line
    assert "function_call(" not in line and "tool_use(" not in line


def test_a_streamed_translated_reply_reports_what_the_prompt_actually_cost(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The reported gap: a translated stream's line carried one input figure and no cache breakdown.

    Responses puts the cached portion in `input_tokens_details` and counts it *inside* `input_tokens`, so reading that usage with Anthropic keys reported a heavily cached prompt as having been sent whole — the one number on the line that decides whether a turn was expensive.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            content=responses_sse_upstream({
                "input_tokens": 138_500,
                "input_tokens_details": {"cached_tokens": 135_000},
                "output_tokens": 2_700,
                "total_tokens": 141_200,
            }),
            headers={"content-type": "text/event-stream"},
        )
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "gpt-model", "messages": [], "stream": True})

    line = _request_lines(caplog.records)[0]
    # What was sent fresh, what came from cache, and the rate that says which of the two dominated.
    assert "↑3.5k+135.0k" in line
    assert "↻97%" in line
    assert "↓2.7k" in line
    assert "↑138.5k" not in line, "the total was being reported as though none of it was cached"


@pytest.mark.asyncio
async def test_a_body_that_fails_to_close_is_still_accounted_for() -> None:
    # Accounting is the one thing this response exists to guarantee, so it cannot be what a failure skips. Closing the body was added here to release the upstream, and a close that raises would otherwise leave the request in the footer with its clock running and no line ever written — the same failure the class was added to prevent, arriving through a different door.
    finished: list[str] = []

    async def body() -> AsyncGenerator[bytes]:
        try:
            yield b"chunk"
        finally:
            raise RuntimeError("closing the body blew up")

    class _Accounting:
        def finish(self) -> None:
            finished.append("finished")

    content = body()
    # Started, so that closing it has a suspended frame to unwind and the `finally` above can run.
    assert await anext(content) == b"chunk"
    response = _AccountedStreamingResponse(content, cast(Any, _Accounting()))

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        raise RuntimeError("the client went away")

    with pytest.raises(RuntimeError) as raised:
        await response({"type": "http", "method": "POST", "path": "/", "headers": []}, receive, send)

    assert finished == ["finished"]
    # The exit that ended the request, not the close that failed on the way out — with the close failure chained on so neither is lost.
    assert str(raised.value) == "the client went away"
    assert str(raised.value.__cause__) == "closing the body blew up"


def test_a_buffered_translated_reply_hands_the_client_anthropic_token_keys(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The body, not just the line. Nothing asserted this contract before, which is how it went wrong.

    Responses counts the cached portion inside `input_tokens` and puts the breakdown in
    `input_tokens_details`. Copied across untouched, the client got keys it has no schema for, no
    `cache_read_input_tokens` at all, and an `input_tokens` meaning the opposite of what Anthropic's
    means — a cached prompt arriving downstream as a full-price one. The streaming path converts, so
    the same route was answering with two different usage contracts depending on one flag.
    """
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "completed",
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]}],
                "usage": {
                    "input_tokens": 138_500,
                    "input_tokens_details": {"cached_tokens": 135_000},
                    "output_tokens": 2_700,
                    "total_tokens": 141_200,
                },
            },
        )
    )

    with caplog.at_level(logging.INFO):
        response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.json()["usage"] == {
        "input_tokens": 3_500,
        "cache_read_input_tokens": 135_000,
        "cache_creation_input_tokens": 0,
        "output_tokens": 2_700,
    }
    # And the line reports the same numbers, because it reads what the client was told.
    assert "↑3.5k+135.0k" in _request_lines(caplog.records)[0]


def test_a_malformed_usage_costs_the_counts_and_not_the_buffered_reply(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    # The reply itself is complete and legal; refusing to deliver it over a count would trade the answer for its accounting.
    client, _ = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "gpt-model",
                "status": "completed",
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]}],
                "usage": {"input_tokens": "lots"},
            },
        )
    )

    with caplog.at_level(logging.INFO):
        response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    assert response.status_code == 200
    assert response.json()["content"] == [{"type": "text", "text": "hi"}]
    assert response.json()["usage"] == {"input_tokens": 0, "output_tokens": 0}


def _upstream_that_goes_quiet(gap: float) -> Callable[[httpx.Request], httpx.Response]:
    """One whole block, then a silence longer than any guard under test, then the rest."""
    whole = sse_upstream("first")
    head, _, tail = whole.partition(b'event: message_delta')

    def handler(_: httpx.Request) -> httpx.Response:
        async def body() -> AsyncIterator[bytes]:
            yield head
            await asyncio.sleep(gap)
            yield b'event: message_delta' + tail

        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    return handler


def _delivered(client: TestClient) -> bytes:
    with client.stream(
        "POST", "/v1/messages", json={"model": "claude-model", "messages": [], "stream": True}
    ) as response:
        return b"".join(response.iter_bytes())


def test_an_upstream_that_goes_quiet_past_the_idle_timeout_is_given_up_on() -> None:
    # `stream_idle` says how long upstream may say nothing mid-turn. It was honoured only on the legacy path; here the setting was read from the config file, validated, and then had no effect on anything.
    client, _ = make_client(
        _upstream_that_goes_quiet(1.5),
        overrides={"upstream_request_timeouts": {"stream_idle": 1}},
    )

    # Given up on the same way every other mid-stream upstream failure is: the turn ends by raising, rather than by quietly rounding off a stream upstream never finished. What that then looks like to a client is the truncation-reporting question — one contract for all of these, not this guard's to answer on its own.
    # Only the raise is asserted. What the client keeps of a turn cut off mid-flight is a property of the wire, and this harness discards the body it had already sent once the app raises, so asserting it here would be asserting the harness.
    with pytest.raises(StreamIdleTimeoutError):
        _delivered(client)


def test_the_bundled_default_leaves_a_quiet_upstream_alone() -> None:
    # 0 is the bundled default and it disables the guard. The frozen invariant is never to false-kill legitimate thinking, so a turn that goes quiet for longer than any timeout would have allowed must still be delivered whole when nobody asked for one.
    client, _ = make_client(_upstream_that_goes_quiet(1.5))

    delivered = _delivered(client)

    assert b'"text":"first"' in delivered
    assert b"message_stop" in delivered


def test_a_per_model_override_decides_the_idle_timeout() -> None:
    # The overrides map is a second wire, and a wire nothing pulls on is a wire nobody notices is attached to the wrong terminal — which is how the sibling map came to be read as the attempt deadline's. The scalar here says "never give up"; only the override can produce this outcome.
    client, _ = make_client(
        _upstream_that_goes_quiet(1.5),
        overrides={
            "upstream_request_timeouts": {"stream_idle": 0, "stream_idle_overrides": {"claude-model": 1}}
        },
    )

    with pytest.raises(StreamIdleTimeoutError):
        _delivered(client)
