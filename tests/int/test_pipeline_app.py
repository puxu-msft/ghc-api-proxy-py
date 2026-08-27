"""End-to-end over the new chain: HTTP in, upstream out, through a real ASGI app.

The upstream is a MockTransport under the real SDKs.
Upstream protocol behaviour is therefore the real thing rather than a friendlier stand-in.
"""

import asyncio
import contextlib
import inspect
import logging
import re
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import h2.errors
import h2.events
import httpcore2
import httpx2
import orjson
import pytest
import structlog
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from prometheus_client import REGISTRY
from pydantic import ValidationError
from starlette.requests import ClientDisconnect, Request

import app.server.routes.inference as inference_route
from app.config.schema import ModelProviderConfig, ProxyConfig
from app.core.chain import Chain
from app.model_provider import GithubCopilotProvider, ModelProvider
from app.model_provider.ghc_client import GhcApiClient, GhcClientConfig
from app.model_provider.ghc_client.tokens import CopilotTokenManager
from app.observability import rejection_capture
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.logging import setup_logging
from app.observability.request_log_file import request_logs_dir
from app.observability.request_trace import REQUEST_LOGGER, RequestTrace
from app.pipeline import driver
from app.pipeline.delivery.assembling import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.formats.anthropic_messages import AnthropicAssembler, AnthropicFramer
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.stream import (
    ContinuationSupport,
    ReplaySupport,
    StreamSettings,
    UpstreamSource,
    stream_delivery,
)
from app.pipeline.delivery_policy import delivery_buffer, stream_settings
from app.server.app_state import CHAIN_STATE_KEY
from app.server.composition import build_chain
from app.server.pipeline_app import (
    create_pipeline_app,
)
from app.server.routes.inference import (
    _AccountedStreamingResponse,  # pyright: ignore[reportPrivateUsage]
    _StreamAccounting,  # pyright: ignore[reportPrivateUsage]
    _tracked_delivery,  # pyright: ignore[reportPrivateUsage]
)
from app.server.routes.router import build_router
from app.server.routes.table import route_for_path
from app.streaming.deadline import ClientDeadlineError
from app.tokenization.state_store import TokenizationStateStore

BASE_URL = "https://copilot.example"

CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "claude-model", "supported_endpoints": ["/v1/messages"]},
        {"id": "gpt-model", "supported_endpoints": ["/responses"]},
        {"id": "cc-model", "supported_endpoints": ["/chat/completions"]},
        {"id": "embed-model", "supported_endpoints": ["/embeddings"]},
        {"id": "mute-model", "supported_endpoints": []},
        # Effort names as the real catalog publishes them, under `capabilities.supports`. Deliberately narrow — no `none`, no `xhigh`, no `max` — so that both "asked for something stronger than this model offers" and "asked for something weaker" are reachable from a test. It is not a copy of any one real model: `grok-4.5` publishes exactly these three, while `gpt-5.3-codex` has `xhigh` as well.
        {
            "id": "reasoning-model",
            "supported_endpoints": ["/responses"],
            "capabilities": {"supports": {"reasoning_effort": ["low", "medium", "high"]}},
        },
    ],
}


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


def make_provider(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    disabled: list[str] | None = None,
) -> tuple[GithubCopilotProvider, httpx2.AsyncClient]:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
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
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    mappings: dict[str, str] | None = None,
    tokenization_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> tuple[TestClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def recording(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        if request.url.path.endswith("/models"):
            # The app refreshes the catalog before it accepts anything, so the stand-in has to answer that too. Left out of `seen`: it is start-up, not the request under test.
            return httpx2.Response(200, json=CATALOG)
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
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []})
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "msg_1"
    assert str(seen[-1].url) == f"{BASE_URL}/v1/messages"


def _beta_strip(model: str, *flags: str) -> dict[str, Any]:
    return {
        "hook_strip_anthropic_request_headers": {
            "strip_anthropic_beta_flags": {model: list(flags)}
        }
    }


def test_a_beta_flag_the_resolved_model_refuses_does_not_reach_upstream() -> None:
    """The config key had no consumer at all until this test existed.

    `hook_strip_anthropic_request_headers` sat in the schema with the operator's measured flag list in `config.example.yaml` and nothing anywhere reading it — the same shape as the guards that were left behind on the legacy chain and only surfaced as production 400s. So the assertion is on the bytes the upstream request carries, not on the function being called.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=_beta_strip("claude-model", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
        headers={"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"},
    )

    assert response.status_code == 200
    assert seen[-1].headers["anthropic-beta"] == "effort-2025-11-24"


def test_a_translated_request_carries_none_of_the_clients_headers() -> None:
    """The whitelist `message-format-reshape.md` gives the translation path, end to end.

    This test used to be called `test_the_strip_applies_on_the_translated_path_too` and asserted the same absent header, which was wrong in a way worth recording: once the whitelist landed, the header was gone before the beta strip ever looked at it, so **disabling the strip in isolation left this green while the direct-path test went red** — measured. It was named for a mechanism it could not observe, and would have gone on reporting that mechanism healthy after it broke.

    There is nothing to fix by re-pointing it at the strip, because on this leg the strip genuinely has nothing to act on. What is left is the whitelist, which is what it now says.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides=_beta_strip("gpt-model", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        },
        headers={
            "anthropic-beta": "context-management-2025-06-27,effort-2025-11-24",
            "anthropic-version": "2023-06-01",
        },
    )

    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/responses"
    assert "anthropic-beta" not in seen[-1].headers
    # Not just the beta header — the whitelist is empty, so none of the client's negotiation travels.
    assert seen[-1].headers.get("anthropic-version") != "2023-06-01"


def test_an_unconfigured_model_still_gets_the_whole_header() -> None:
    """The default has to be inert: this map exists to remove four flags, not to become a gate."""
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=_beta_strip("some-other-model", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
        headers={"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"},
    )

    assert response.status_code == 200
    assert (
        seen[-1].headers["anthropic-beta"]
        == "context-management-2025-06-27,effort-2025-11-24"
    )


def test_the_table_is_keyed_on_the_model_the_attempt_is_sent_to() -> None:
    """Ruled 2026-08-22: the table matches the actual upstream attempt, so an alias is looked through.

    The consequence is worth pinning rather than leaving implicit. An entry written under a name `model_mappings` maps away never fires — and nothing reports that it did not, which is why the counter in the sibling test exists.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        mappings={"claude-alias": "claude-model"},
        overrides=_beta_strip("claude-model", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-alias", "messages": [{"role": "user", "content": "hi"}]},
        headers={"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"},
    )

    assert response.status_code == 200
    assert seen[-1].headers["anthropic-beta"] == "effort-2025-11-24"


def test_a_table_keyed_on_an_alias_does_not_fire() -> None:
    """The other side of the same ruling, and the shape the authoritative config is currently in.

    `config.example.yaml` writes the table under `claude-sonnet-4.6` and also maps `claude-sonnet-4.6: claude-sonnet-5`, so that entry is inert as written. That is the config's own question, not something to paper over here — but it must not be a surprise, so it is a test.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        mappings={"claude-alias": "claude-model"},
        overrides=_beta_strip("claude-alias", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-alias", "messages": [{"role": "user", "content": "hi"}]},
        headers={"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"},
    )

    assert response.status_code == 200
    assert (
        seen[-1].headers["anthropic-beta"]
        == "context-management-2025-06-27,effort-2025-11-24"
    )


def test_a_stripped_flag_is_counted_under_the_configured_spelling() -> None:
    """Removing a capability silently is what an operator has no way to notice. The counter is the notice.

    The label carries the operator's spelling rather than the client's: a client-controlled label value has no bound on its series count.
    """
    before = (
        REGISTRY.get_sample_value(
            "ghc_proxy_beta_flags_stripped_total",
            {"model": "claude-model", "flag": "context-management-2025-06-27"},
        )
        or 0.0
    )
    client, _ = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=_beta_strip("claude-model", "context-management-2025-06-27"),
    )
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
        # Spelled differently from the config on purpose: the label must still be the config's.
        headers={"anthropic-beta": "Context-Management-2025-06-27"},
    )

    assert response.status_code == 200
    after = REGISTRY.get_sample_value(
        "ghc_proxy_beta_flags_stripped_total",
        {"model": "claude-model", "flag": "context-management-2025-06-27"},
    )
    assert after == before + 1


def test_anthropic_request_for_a_responses_model_is_translated() -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
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
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
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
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            # Explicitly on: the switch defaults to off, so without this the gate refuses before the model list is ever consulted and the test stops discriminating what it names.
            "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["gpt-model"],
                }
            }
        },
    )
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
    """Driven by a real upstream recording: `tests/int/cassettes/responses_web_search_stream.json`.

    A `web_search_call` has no delta events and arrives with only an id, a status and a type on `output_item.added` — the query appears for the first time on `done`. Assembled the ordinary way, from the draft the `added` opened, it closed as an empty text block: the client got a blank content block ahead of every answer, and the one fact the item carried was thrown away.

    The cassette is used rather than a hand-written stream because that asymmetry is exactly the kind of thing a stand-in gets wrong — it would have been written from what the events are assumed to carry.
    """
    cassette = orjson.loads(Path("tests/int/cassettes/responses_web_search_stream.json").read_bytes())
    interaction = next(
        i for i in cassette["interactions"] if "responses" in i["request"]["path"]
    )
    sse = "".join(chunk["text"] for chunk in interaction["response"]["chunks"]).encode()

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        ),
        overrides={
            # Explicitly on: the switch defaults to off, so without this the gate refuses before the model list is ever consulted and the test stops discriminating what it names.
            "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["gpt-model"],
                }
            }
        },
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
    # No block may be delivered empty: that was the symptom, and it is invisible in a test that only checks the answer arrived.
    assert all(text for text in deltas), deltas


def test_hosted_web_search_is_off_until_the_config_says_otherwise() -> None:
    """The default. A search declaration with nothing configured is answered as a failed tool, and upstream is never asked.

    Ruled 2026-08-21: the Responses leg really does execute a search, but what this proxy does with the answer is partial — a line of text where the protocol defines a `server_tool_use` / `web_search_tool_result` pair, `url_citation` annotations unread, `max_uses` and the domain lists unsendable. Off is what keeps that from being what every request gets.

    Off is not the same as removing the declaration and carrying on. A Claude Code search is its own sub-request carrying nothing but the search, so one stripped of it answers from memory under a heading the client reads as search results — which is why `seen == []` is half the assertion.

    The model is put on the supported list on purpose, and `hosted_web_search` is the one thing left unset. Without that this test passes for the wrong reason: the default patterns do not claim `gpt-model`, so flipping the switch's default to on left it green — measured. The list has to say yes for the switch to be the only thing saying no.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["gpt-model"],
                }
            }
        },
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [
                {"role": "user", "content": "Perform a web search for the query: bun"}
            ],
            "max_tokens": 1024,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )

    assert response.status_code == 200, "an HTTP error here is retried by the client"
    assert seen == [], "a disabled search still reached upstream"
    blocks = orjson.loads(response.content)["content"]
    assert [block["type"] for block in blocks] == [
        "server_tool_use",
        "web_search_tool_result",
    ]
    assert blocks[1]["content"]["error_code"] == "unavailable"


def test_a_search_that_cannot_run_is_answered_as_a_failed_tool_not_an_error() -> None:
    """The client issues a search as its own sub-request and treats an HTTP error as a transport problem worth retrying — three times, in the one case on record. A search this endpoint cannot run will not start working on the third attempt.

    A failed *tool* is not retried. Anthropic defines the shape for exactly this: a 200 carrying `server_tool_use` paired with a `web_search_tool_result` whose content is a single `web_search_tool_result_error` object. So the reply says the search failed in the protocol's own words instead of handing the model an HTTP error string to interpret.

    Asserted on upstream never being called as well, because the whole point is that nothing was asked to answer this from memory.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            # Explicitly on: the switch defaults to off, so without this the gate refuses before the model list is ever consulted and the test stops discriminating what it names.
            "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["some-other-model"],
                }
            }
        },
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [
                {"role": "user", "content": "Perform a web search for the query: bun"}
            ],
            "max_tokens": 1024,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )

    assert response.status_code == 200, "an HTTP error here is retried by the client"
    assert seen == [], "the model was asked to answer a search it could not run"
    blocks = orjson.loads(response.content)["content"]
    assert [block["type"] for block in blocks] == [
        "server_tool_use",
        "web_search_tool_result",
    ]
    assert blocks[0]["name"] == "web_search"
    # The result references its call, or it refers to nothing.
    assert blocks[1]["tool_use_id"] == blocks[0]["id"]
    # A single object, not a list: `content: []` is the documented shape for a search that ran and matched nothing, which would be a claim about the web rather than about us.
    assert blocks[1]["content"] == {
        "type": "web_search_tool_result_error",
        "error_code": "unavailable",
    }


def test_a_streamed_search_that_cannot_run_is_answered_the_same_way() -> None:
    """The sub-requests that carry a search are all `stream: true`, measured over 190 of them, so the synthesised reply has to survive the streaming path rather than only the buffered one."""
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            # Explicitly on: the switch defaults to off, so without this the gate refuses before the model list is ever consulted and the test stops discriminating what it names.
            "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["some-other-model"],
                }
            }
        },
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [
                {"role": "user", "content": "Perform a web search for the query: bun"}
            ],
            "max_tokens": 1024,
            "stream": True,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )

    assert response.status_code == 200
    assert seen == []
    starts = [
        orjson.loads(line[6:])["content_block"]
        for line in response.text.splitlines()
        if line.startswith("data: ") and '"content_block_start"' in line
    ]
    assert [block["type"] for block in starts] == [
        "server_tool_use",
        "web_search_tool_result",
    ]
    assert starts[1]["content"]["error_code"] == "unavailable"


def test_the_shape_claude_code_really_sends_reaches_upstream_as_a_search() -> None:
    """The end-to-end case the whole feature exists for, in the shape it actually arrives in.

    Measured over 190 real sub-requests on 2026-08-20: `tools` holds exactly one entry, always with a non-empty `allowed_domains`, and 95 of them force the choice. Every earlier test here used a shape nobody sends — and with the domain policy defaulting to `error`, that difference was the difference between "web search works" and "web search never works".

    The forced choice is asserted beside the tools because the sub-request has no other purpose: it carries a turn reading `Perform a web search for the query: X`, and a model no longer obliged to search may answer from memory while the client still labels the reply as search results.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            # Explicitly on: the switch defaults to off, so without this the gate refuses before the model list is ever consulted and the test stops discriminating what it names.
            "model_translation": {"to_openai_responses": {"hosted_web_search": True}},
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["gpt-model"],
                }
            }
        },
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": "You are an assistant.",
            "messages": [
                {"role": "user", "content": "Perform a web search for the query: bun 1.3"}
            ],
            "max_tokens": 1024,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 8,
                    "allowed_domains": ["docs.anthropic.com"],
                    "blocked_domains": [],
                }
            ],
            "tool_choice": {"type": "tool", "name": "web_search"},
        },
    )

    assert response.status_code == 200
    sent = orjson.loads(seen[-1].read())
    assert sent["tools"] == [{"type": "web_search"}]
    assert sent["tool_choice"] == {"type": "web_search"}


def test_a_domain_restriction_refuses_before_upstream_is_called() -> None:
    """Under `web_search_domain_restrictions: error`, which is not the default and is what the spec's D1 ruling asked for.

    Asserted on `seen` being empty as much as on the status: the refusal is only worth anything if it happens *before* the call. A 400 raised after upstream had already searched would tell the client its restriction failed while the model had already read the pages — which is the one thing this setting exists to prevent.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides={
            "model_translation": {
                "to_openai_responses": {
                    "hosted_web_search": True,
                    "web_search_domain_restrictions": "error",
                }
            },
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": BASE_URL,
                    "models_support_web_search": ["gpt-model"],
                }
            },
        },
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "allowed_domains": ["example.com"],
                }
            ],
        },
    )

    assert response.status_code == 400
    assert seen == [], "upstream was called despite the request being unserviceable"
    body = orjson.loads(response.content)["error"]
    # A stable code and the field that caused it: a client matching on the English would break the first time the wording changed, and one told only "bad request" cannot find which tool it was.
    assert body["code"] == "server_tool_constraint_not_representable"
    assert body["param"] == "tools.web_search_20250305.allowed_domains"


def test_model_mapping_is_applied_before_the_upstream_call() -> None:
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1"}),
        mappings={"opus": "claude-model"},
    )
    response = client.post("/v1/messages", json={"model": "opus", "messages": []})

    assert response.status_code == 200
    assert '"claude-model"' in seen[-1].read().decode()


def test_openai_group_is_served_under_every_compatible_prefix() -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    for prefix in ("", "/v1", "/openai/v1"):
        response = client.post(f"{prefix}/responses", json={"model": "gpt-model", "input": []})
        assert response.status_code == 200
    assert len(seen) == 3


def test_model_without_the_capability_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mute-model", "messages": []})

    assert response.status_code == 400
    # The dialect's own vocabulary, not this project's class name. `CapabilityMissing` used to reach the wire, which made an exception's name part of the public contract — renaming the class would have been a wire change.
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "invalid_request"
    # Fail closed means nothing was sent, not that upstream rejected it.
    assert seen == []


def test_unknown_model_is_refused_before_the_network() -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={}))
    response = client.post("/v1/messages", json={"model": "mystery", "messages": []})

    # **404 rather than 400.** The model named is not in the catalog, which is "no such thing" and not "your body is malformed" — and `CapabilityMissing` above is exactly the distinction 400 was blurring. Neither SDK retries either status, so what changes is the exception class the client catches.
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found_error"
    assert seen == []


def test_missing_model_is_rejected_by_inbound_parsing() -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={}))
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
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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


def test_upstream_error_status_reaches_the_client_as_upstream_sent_it() -> None:
    """**Behaviour change**: this used to answer 502 whatever upstream said.

    502 means the gateway itself broke. Upstream said 500, which means upstream broke — and on a direct path the client is owed upstream's own answer, body included. The old name of this test asserted the very thing that was wrong with it.
    """
    client, _ = make_client(lambda _: httpx2.Response(500, json={"error": "upstream boom"}))
    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})
    assert response.status_code == 500
    assert response.json() == {"error": "upstream boom"}


def test_unknown_path_is_not_served() -> None:
    client, _ = make_client(lambda _: httpx2.Response(200, json={}))
    assert client.post("/nope", json={"model": "claude-model"}).status_code == 404


@pytest.mark.parametrize("path", ["/embeddings", "/v1/embeddings", "/openai/v1/embeddings"])
def test_embeddings_endpoint_is_served(path: str) -> None:
    client, seen = make_client(lambda _: httpx2.Response(200, json={"data": []}))
    response = client.post(path, json={"model": "embed-model", "input": "hi"})
    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/embeddings"


CHAT_COMPLETIONS_SSE = (
    b'data: {"id":"cc-1","object":"chat.completion.chunk","choices":'
    b'[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
    b'data: {"id":"cc-1","object":"chat.completion.chunk","choices":'
    b'[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}\n\n'
    b'data: {"id":"cc-1","object":"chat.completion.chunk","choices":'
    b'[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
    b"data: [DONE]\n\n"
)


@pytest.mark.parametrize(
    "path", ["/chat/completions", "/v1/chat/completions", "/openai/v1/chat/completions"]
)
def test_chat_completions_endpoint_is_served(path: str) -> None:
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "cc-1", "object": "chat.completion"})
    )
    response = client.post(path, json={"model": "cc-model", "messages": []})
    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/chat/completions"
    assert response.json() == {"id": "cc-1", "object": "chat.completion"}


def test_chat_completions_streams_are_delivered_whole_and_verbatim() -> None:
    """Nothing here can find a block boundary in this dialect, so the whole stream is one delivery.

    Before 2026-08-22 these bytes went into `AnthropicAssembler`, whose event names none of them match, so no block was ever completed and the client got a 200, a `text/event-stream` content type, and zero bytes — no error frame either, because delivery only writes one once a message has started. Measured, then ruled: buffer and forward until someone writes a framer for this dialect.

    Byte-for-byte rather than event names, because the promise being kept is that nothing was reinterpreted on the way through — `data: [DONE]` included, which has no equivalent in any shape this proxy assembles.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(
            200,
            content=CHAT_COMPLETIONS_SSE,
            headers={"content-type": "text/event-stream"},
        )
    )
    response = client.post(
        "/chat/completions",
        json={"model": "cc-model", "messages": [], "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert str(seen[-1].url) == f"{BASE_URL}/chat/completions"
    assert response.content == CHAT_COMPLETIONS_SSE


def test_the_one_shot_guard_comment_says_that_arrived_bytes_are_delivered() -> None:
    """This path has no error carrier, but it does send the upstream bytes that arrived before the guard fired.

    A source assertion is intentional here: the defect is a false source comment, so reverting only that comment cannot be detected through runtime behaviour — a test of what the code *does* stays green while the code's description of itself goes back to being wrong.

    The two assertions do different jobs, and only the second one is allowed to be strict. The first pins the *claim* rather than any particular sentence, so the comment can be rewritten freely as long as it still says bytes arrive; wording this one as an exact phrase would make every honest edit look like a regression. The second names the false sentence itself, because that is the one string this comment must never contain again.
    """
    source = inspect.getsource(inference_route)
    guard_comment = next(
        line for line in source.splitlines() if "no framer for this leg" in line
    )

    assert "arrived" in guard_comment and "bytes" in guard_comment
    assert "whatever had been buffered, which is nothing" not in source


@pytest.mark.parametrize(
    ("path", "model", "upstream", "body"),
    [
        ("chat/completions", "cc-model", "/chat/completions", {"messages": []}),
        ("responses", "gpt-model", "/responses", {"input": []}),
        ("embeddings", "embed-model", "/embeddings", {"input": "hi"}),
    ],
)
def test_an_azure_deployment_path_names_the_model(
    path: str, model: str, upstream: str, body: dict[str, Any]
) -> None:
    """Azure sends an OpenAI body with no model in it and names the deployment in the URL instead.

    The assertion is on the bytes that crossed rather than on a 200, because a route that reached upstream with the wrong model would pass either way — and "which model" is the entire content of what these three paths add over the ones above them.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "ok", "data": []}))
    response = client.post(f"/openai/deployments/{model}/{path}", json=body)

    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}{upstream}"
    assert orjson.loads(seen[-1].read())["model"] == model


def test_the_azure_paths_are_not_mounted_under_the_openai_prefixes() -> None:
    """They are already fully qualified, so `/v1` and `/openai/v1` in front would be a second spelling nothing serves.

    Both layers are asserted separately, and that separation is the point. A 404 alone cannot tell "never registered" from "registered but missing from the lookup" — the second answers 404 too, from `_dispatch`'s defensive branch, having gone all the way through `serve`. A review reproduced exactly that by mounting the wrong template on a real app and leaving `_BY_PATH` alone: HTTP 404, no upstream request, and this test green.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "ok"}))
    for prefix in ("/v1", "/openai/v1"):
        wrong = f"{prefix}/openai/deployments/gpt-model/responses"
        assert client.post(wrong, json={"input": []}).status_code == 404
        assert route_for_path(f"{prefix}/openai/deployments/{{deployment}}/responses") is None
    assert seen == []


def test_what_is_mounted_and_what_can_be_looked_up_are_the_same_set() -> None:
    """The one failure neither side can report on its own.

    `build_router` registers paths and `route_for_path` maps them back, and until `expanded_paths` existed each applied its own rule. A path in the first set but not the second reaches `serve` and comes back 404 as if it were never served; one in the second but not the first is a lookup for something nobody can reach. Both are silent, so the guard is the equality rather than a probe of either side.

    Read off the router's own POST routes rather than off `ROUTES`, because the registration is what a client meets. The ops surface arrives through `include_router` and leaves a single object with `path=None` behind, which is why it is filtered out rather than expected to appear.
    """
    mounted = {
        route.path
        for route in build_router().routes
        if isinstance(route, APIRoute) and "POST" in (route.methods or set())
    }
    assert mounted
    assert {path for path in mounted if route_for_path(path) is not None} == mounted


def test_a_gemini_path_says_not_implemented_rather_than_not_found() -> None:
    """`api.md` ratifies the path and no translator answers to its format yet.

    Three codes are distinguishable here and only one is right. 404 would make a ratified endpoint indistinguishable from one this proxy does not have. 400 is what a missing translator produces on its own, and that blames the client's body for a capability this proxy has not built. 501 is the one that says what is true, and the request is refused before the body is parsed — asserted by sending a body that is not valid JSON, which would be a 400 on any implemented route.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "ok"}))
    for suffix in ("generateContent", "streamGenerateContent", "countTokens"):
        response = client.post(f"/v1beta/models/gemini-pro:{suffix}", content=b"{not json")
        assert response.status_code == 501
        said = response.json()["error"]["message"]
        assert "not implemented" in said
        # The URL the client used, not the route table's own template. A message naming `{model}` hands back a spelling only this repository understands.
        assert f"/v1beta/models/gemini-pro:{suffix}" in said
        assert "{" not in said
    # A model that contains colons is still one model. The greedy segment takes everything up to the method, so this must not be the price of bounding the method set.
    assert client.post("/v1beta/models/vendor:family:countTokens", json={}).status_code == 501
    assert seen == []


@pytest.mark.parametrize(
    "path",
    [
        "/v1beta/models/gemini-pro:unknownMethod",
        "/v1beta/models/gemini-pro",
        "/v1beta/models/something-else",
    ],
)
def test_a_gemini_method_api_md_does_not_name_is_not_served_at_all(path: str) -> None:
    """The boundary the three explicit templates exist to draw, and the reason a catch-all was wrong.

    `api.md` names three methods. Registered as one `{model_and_method}` segment, all of these answered 501 — the proxy claiming a ratified endpoint it has none of, and the method set ceasing to be a boundary anything enforced. The positives above cannot see this: three legal suffixes are three samples of the same catch-all.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "ok"}))
    assert client.post(path, json={}).status_code == 404
    assert seen == []


def test_translated_route_answers_in_the_format_the_client_asked_in() -> None:
    # The earlier translation test only checked the request. Half a crossing means the client gets a Responses body it never asked for and cannot parse.
    client, _ = make_client(
        lambda _: httpx2.Response(
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
    """`.dev/docs/anthropic-responses-bridge/spec.md`: an incomplete response due to the output-token limit is max_tokens downstream — and then the turn is handed back, so `tool_use` is what reaches the wire.

    The mapping itself is asserted where it happens, in `tests/unit/pipeline/translation_driver/test_responses_stop_reason.py`. What this holds is the ending a buffered reply gets once that mapping has said the turn ran out of room: the client is handed a way to carry it on, exactly as a streamed one is. Ruled 2026-08-22.
    """
    client, _ = make_client(
        lambda _: httpx2.Response(
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
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stop_reason"] == "tool_use"
    handed = body["content"][-1]
    assert handed["type"] == "tool_use"
    assert handed["name"] == TOOL_NAME
    assert handed["input"]["category"] == "max_tokens"
    # Three, not zero. An empty conversation makes this assertion vacuous — both the client's count and the translated body's agree on nothing at all — which is the shape that let the same defect through on the streamed side.
    assert handed["input"]["num_messages"] == 3
    # The one block upstream produced is still there: dropping is only for a block upstream itself cut short, and only when something whole came before it.
    assert body["content"][0] == {"type": "text", "text": "cut"}
    # Neither a success nor a failure, the same as the streamed ending.
    record = _records()[-1]
    assert record["status"] == "retry"
    # And the line describes what *upstream* produced, not what this side appended to it. The streamed path reads its summary off the assembler, which never sees the synthesised block; reading this one off the finished payload made the same upstream reply report two different things depending on which route carried it — and report a tool the model never asked for.
    assert record["stop_reason"] == "max_tokens"
    assert record["blocks"] == 1
    assert TOOL_NAME not in record.get("tools", [])


def test_untranslated_route_body_is_returned_unchanged() -> None:
    client, _ = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "custom": {"kept": True}})
    )
    response = client.post("/v1/messages", json={"model": "claude-model", "messages": []})
    assert response.json()["custom"] == {"kept": True}


def test_upstream_429_is_seen_by_the_rate_limiter() -> None:
    # A 429 must reach the limiter, not merely surface as an error.
    from app.pipeline.rate_limiting import RateLimitMode

    provider, http_client = make_provider(
        lambda request: (
            httpx2.Response(200, json={"token": "c", "expires_at": 5000, "refresh_in": 1500})
            if request.url.host == "api.github.com"
            else httpx2.Response(429, json={"error": "slow down"})
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

    assert response.status_code == 429
    assert chain.rate_limiter_for("ghc").mode is RateLimitMode.LIMITED


def test_a_rate_limit_that_runs_out_of_retries_still_reaches_the_client_as_one() -> None:
    """Running out of retries does not change what upstream said, and the client can still act on it.

    This used to be a 502 with no headers: the abort that ended the retry sequence replaced the failure that ended it, so a client that could have backed off for the named interval was told the proxy had broken instead. The budget is set to zero here so the first failure is also the last one.
    """
    from app.pipeline.rate_limiting import RateLimitMode

    provider, http_client = make_provider(
        lambda request: (
            httpx2.Response(200, json={"token": "c", "expires_at": 5000, "refresh_in": 1500})
            if request.url.host == "api.github.com"
            else httpx2.Response(429, json={"error": "slow down"}, headers={"retry-after": "17"})
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

    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    # Upstream's own body, because this is a direct path. It used to be this proxy's envelope with the abort's wording inside — which said which *budget* ran out, an operator's fact that the client could do nothing with. The operator still gets it: it is on the completion line, which is where a reader of budgets looks.
    assert response.json() == {"error": "slow down"}
    assert chain.rate_limiter_for("ghc").mode is RateLimitMode.LIMITED


def test_upstream_503_does_not_enter_limited_mode() -> None:
    # The spec keeps 503 out of the reactive triggers.
    from app.pipeline.rate_limiting import RateLimitMode

    provider, http_client = make_provider(
        lambda request: (
            httpx2.Response(200, json={"token": "c", "expires_at": 5000, "refresh_in": 1500})
            if request.url.host == "api.github.com"
            else httpx2.Response(503, json={"error": "unavailable"})
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
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 4242}))
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

    The reply says `estimated`, because an estimate presented as a measurement is worse than no answer: the caller sizes its request against it.
    """
    client, _ = make_client(lambda _: httpx2.Response(500, json={"error": "upstream is down"}))
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
        lambda _: httpx2.Response(200, json={"input_tokens": 7}),
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

    The default supplied to make the body countable must stay on this side of the wire. Asserting only that the request succeeds cannot tell the two apart — a version that mutated the outbound payload passes that just as well.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 11}))
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
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 99}))
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
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 1}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-model", "messages": "not a list of messages"},
    )

    assert response.status_code == 400
    assert seen == [], "an uncountable body must not reach upstream"


def test_count_tokens_refuses_a_model_without_the_messages_capability() -> None:
    """Refused by routing, before any counter is chosen.

    The refusal here comes from `decide_route`, not from the provider's own gate — a mutation that removes the provider check leaves this test green. The provider gate has its own test in `tests/unit/test_model_provider.py`.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 1}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "mute-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400
    assert seen == []


def test_what_the_calibrator_learns_survives_a_restart(tmp_path: Path) -> None:
    """Learning that dies with the process makes `local` worse the more the service restarts.

    Two apps over the same state file. The first is taught by a real upstream count; the second never reaches upstream at all, so the number it returns can only have come from disk.
    """
    state = tmp_path / "tokenization.json"
    body = {"model": "claude-model", "messages": [{"role": "user", "content": "hello there"}]}

    untaught, _ = make_client(
        lambda _: httpx2.Response(503, json={"error": "down"}),
        tokenization_path=tmp_path / "empty.json",
    )
    with untaught:
        before = untaught.post("/v1/messages/count_tokens", json=body).json()["input_tokens"]

    teacher, _ = make_client(
        lambda _: httpx2.Response(200, json={"input_tokens": before * 10}),
        tokenization_path=state,
    )
    with teacher:
        assert teacher.post("/v1/messages/count_tokens", json=body).status_code == 200
    assert state.is_file(), "the lifespan must flush what was learnt"

    successor, seen = make_client(
        lambda _: httpx2.Response(503, json={"error": "down"}),
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
    client, seen = make_client(lambda _: httpx2.Response(400, text=refusal))

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


def test_a_refused_body_is_kept_as_the_bytes_that_actually_crossed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The capture must hold the wire body, not only a dict that would have to be serialized again to become one.

    `payload` beside it is the request as the pipeline built it, and re-encoding that dict is a guess at what went out: key order, separators and whatever the SDK did on the way are all decided after the pipeline is finished with it. Only the *length* of the real bytes was ever recorded, on the completion line, which cannot be compared against anything.

    Asserted through the app for the same reason as the test above — the bytes are read at the SDK error boundary, and a boundary nobody reaches looks exactly like a working one — and against `seen`, which is httpx's own record of the request it sent.
    """
    monkeypatch.setattr(rejection_capture, "user_data_path", lambda: tmp_path)
    client, seen = make_client(lambda _: httpx2.Response(400, text='{"error":"no"}'))

    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400
    captures = list((tmp_path / "rejected").glob("*.json"))
    assert len(captures) == 1, f"nothing kept the refused body: {captures}"
    record = orjson.loads(captures[0].read_bytes())
    wire = seen[-1].read()
    assert wire, "this test is only meaningful if a body really went out"
    assert record["sent"].encode() == wire
    assert record["sent_bytes"] == len(wire)


def thinking(text: str = "t", signature: str = "sig") -> dict[str, Any]:
    return {"type": "thinking", "thinking": text, "signature": signature}


def test_adjacent_thinking_blocks_are_separated_before_they_reach_upstream() -> None:
    """Upstream rejects adjacent thinking blocks with a 400 the client cannot act on.

    Asserted against the body that actually went out rather than against the fixup in isolation:
    the fixup has to run *before* translation, and a test of the function alone cannot tell whether the wiring put it there or after.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
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
    # Neither signature nor text: it carries nothing upstream can use, and it would otherwise be spent as a separator between two real ones.
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
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

    Uses adjacent thinking blocks rather than text ones on purpose. `destack_content` is a no-op on content with no adjacent thinking blocks, so a user turn carrying two text blocks passes this test whether the role is checked or not — it cannot tell the guard from its absence.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
    original = [thinking("one"), thinking("two")]
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [{"role": "user", "content": original}]},
    )

    assert response.status_code == 200
    assert orjson.loads(seen[-1].read())["messages"][0]["content"] == original


def layout(value: object) -> dict[str, Any]:
    return {"hook_fix_anthropic_request": {"thinking": {"assistant_message_layout": value}}}


def assistant_blocks(seen: list[httpx2.Request]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], orjson.loads(seen[-1].read())["messages"][0]["content"])


def send_stacked(client: TestClient) -> httpx2.Response:
    """Two adjacent thinking blocks with a real text block after them.

    The real block is what tells the two layouts apart: `move_and_synthetic` moves it between the thinking blocks, `synthetic_only` leaves it where it is and inserts a marker. Without it both layouts produce the same three blocks and no test can distinguish them.
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
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=layout("move_and_synthetic"),
    )
    assert send_stacked(client).status_code == 200

    blocks = assistant_blocks(seen)
    assert [block["type"] for block in blocks] == ["thinking", "text", "thinking"]
    # The real block became the separator rather than a synthetic marker being inserted.
    assert blocks[1]["text"] == "real"


def test_synthetic_only_leaves_the_real_block_where_it_was() -> None:
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
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
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=layout(False),
    )
    assert send_stacked(client).status_code == 200
    assert [block["type"] for block in assistant_blocks(seen)] == ["thinking", "thinking", "text"]


def test_an_undefined_layout_value_is_refused() -> None:
    # `true` is not one of the three spellings the spec defines; accepting it would silently rewrite request bodies under a config the operator got wrong.
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


def stream_thinking(client: TestClient) -> httpx2.Response:
    return client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )


def signature_compat(value: object) -> dict[str, Any]:
    return {"hook_fix_anthropic_sse": {"thinking": {"content_block_start_compat": value}}}


def test_the_signature_shim_is_driven_by_configuration() -> None:
    """Turning it off in the config must reach the frames the client receives.

    The shim's default matches `StreamSettings`' default, so a test that never sets a non-default value passes whether the config is read or ignored — which is exactly the wiring under test.
    """
    def upstream(request: httpx2.Request) -> httpx2.Response:
        del request
        return httpx2.Response(
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

    def upstream(_: httpx2.Request) -> httpx2.Response:
        inflight.extend(entry.model for entry in _registry(client).snapshot())
        return httpx2.Response(200, json={"id": "msg_1", "content": []})

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
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # A success names the model instead of the route, and carries the status and how long it took.
    assert lines[0].startswith("H1/H1 200 anthropic-messages/claude-model ")


def test_a_token_count_says_it_was_one_and_which_counter_answered(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The reported line, served: `H1 200 anthropic-messages/claude-opus-5 1.2s ↑19.7k` and nothing more.

    Read at the console it looked like a delivered turn that had lost every reply field, and it was a count — which has no reply to lose. The count branch returns before anything is sent or received on the delivery path, so it filled in none of the fields that branch fills in, and the successful-line shape had already dropped the route that would have said so.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 4242}))

    with caplog.at_level(logging.INFO):
        client.post(
            "/v1/messages/count_tokens",
            json={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # Both legs, because this count really did go upstream, and the counter named because the number is upstream's own measurement.
    assert lines[0].startswith("H1/H1 200 anthropic-messages-count-tokens/claude-model ")
    assert lines[0].endswith("provider(ghc)")
    # Both directions of that leg. One of them alone would say, by this line's own convention, that nothing came back — from the exchange that produced the number on the line.
    assert re.search(r"[↑>][\d.]+(B|KB|MB)\b", lines[0]), "the body sent upstream is what the count was measured on"
    assert re.search(r"[↓<][\d.]+(B|KB|MB)\b", lines[0]), "and upstream's answer is where the number came from"


def test_a_count_upstream_could_not_answer_is_reported_as_an_estimate(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """Upstream failed, the estimator answered, and the client's number is marked `estimated`.

    Not a *refusal*, which is a settled word here: `pipeline/count_tokens.py` lets a `ProviderError` — an unknown model, a missing capability — travel out rather than degrading, so a refused count never reaches the estimator and never produces this line at all. This is the other case, where upstream was reachable and broke.

    The counter's name and its reason are the whole of what says so. The upstream leg does not: `send_anthropic_count_tokens` raises an error status as a pipeline error, so no response reaches the code that records which leg was flown, and this line looks like one that never left the process. Without the `ghc-failed` in front of it, it would also read exactly like a route that has no upstream counter and was always going to estimate.
    """
    client, _ = make_client(lambda _: httpx2.Response(500, json={"error": "upstream is down"}))

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages/count_tokens",
            json={"model": "claude-model", "messages": [{"role": "user", "content": "hello there"}]},
        )

    assert response.json()["estimated"] is True
    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    assert lines[0].startswith("H1 200 anthropic-messages-count-tokens/claude-model ")
    assert lines[0].endswith("provider(ghc-failed,local)")


def test_a_count_with_no_upstream_counter_says_that_rather_than_a_failure(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The ordinary case that must not read as an incident.

    `gpt-model` is served by translating to `/responses`, which has no count endpoint at all, so this route estimates every time and is working as configured. It shares `provider(local)` with an upstream that was asked and broke, and the reason is the only thing that separates them — which is why the reason is on the line rather than only in the attempts trail nobody reads.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 99}))

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages/count_tokens",
            json={"model": "gpt-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.json()["estimated"] is True
    assert seen == [], "no counter was asked, so nothing should have gone upstream"
    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # One leg, because nothing was sent, and the reason says that is by design rather than a failure.
    assert lines[0].startswith("H1 200 anthropic-messages-count-tokens/gpt-model ")
    assert lines[0].endswith("provider(no-counter,local)")


def test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    """The other half of the leg's meaning: it says upstream *responded*, not that upstream answered.

    A 200 carrying no usable `input_tokens` is a reply — it has a protocol, a size, and a round trip behind it — and the count still falls to the estimator. Reporting no leg here would say the request never left the process, which is the reading that sent somebody looking at the wrong end of the exchange in the first place.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"input_tokens": 0}))

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages/count_tokens",
            json={"model": "claude-model", "messages": [{"role": "user", "content": "hello there"}]},
        )

    assert response.json()["estimated"] is True
    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # Both legs and both directions, next to the counter that says the number on the line is not upstream's.
    assert lines[0].startswith("H1/H1 200 anthropic-messages-count-tokens/claude-model ")
    assert lines[0].endswith("provider(ghc-failed,local)")
    assert re.search(r"[↑>][\d.]+(B|KB|MB)\b", lines[0])
    assert re.search(r"[↓<][\d.]+(B|KB|MB)\b", lines[0])


def test_a_refused_request_is_reported_with_its_route_and_reason(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages", json={"model": "no-such-model", "messages": []})

    lines = _request_lines(caplog.records)
    assert len(lines) == 1
    # A failure keeps `METHOD /path`, because that is what has to be reproduced, and ends in the reason. One protocol label rather than a pair: this request never reached upstream, so there is no second leg to name.
    assert lines[0].startswith("H1 404 POST /v1/messages ")
    assert "no-such-model" in lines[0]


def test_an_upstream_refusal_is_described_by_the_same_error_info_on_the_line_and_wire(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The completion line and the client response are two presentations of the same failure, so both must read the message from the same `ErrorInfo`.

    The SDK exception has another true but incompatible string representation: Python dict repr with single quotes and an `Error code` prefix. Reading that on one surface and `ErrorInfo.message` on the other made the two accounts impossible to compare.
    """
    upstream_message = "Invalid 'max_output_tokens': expected at least 16"
    client, _ = make_client(
        lambda _: httpx2.Response(
            400,
            json={"error": {"message": upstream_message, "code": "invalid_request_body"}},
        )
    )

    with caplog.at_level(logging.INFO):
        response = client.post("/v1/messages", json={"model": "gpt-model", "messages": []})

    message = cast(str, response.json()["error"]["message"])
    (line, status), = _request_outcomes(caplog.records)
    assert status == "fail"
    assert message == f"upstream returned 400: {upstream_message}"
    assert f": {message} req=" in line
    assert "Error code: 400" not in line


def test_a_request_that_raised_on_its_way_out_still_writes_its_one_line(
    request_log: None, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exit that used to write nothing at all.

    `log_completion` says every exit path produces exactly one line, and every test around this one checks a path that reaches a `return`. An exception leaving `_dispatch` skipped all of them: the slot was released and the request vanished, and the only trace left was a traceback under the server's own logger with none of this request's identity on it.

    **The vehicle changed on 2026-08-24, and why is worth keeping.** This used to need no patching: upstream answered 200 and called a non-JSON body JSON, and `response.json()` in the buffered branch was not inside a `try`, so the decode error went straight out. That is now caught and answered as a 502 in the client's own dialect, which is the right behaviour and leaves this property without a naturally-occurring vehicle — four other malformed replies were tried and all of them are answered rather than raised.

    So the failure is injected, at the one place that still stands for "something nobody anticipated". What is being checked is unchanged and is not about which exception it is: an exit by exception is an exit, and it owes the same one line as a `return`.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))

    def exploding(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("nobody anticipated this")

    monkeypatch.setattr("app.server.routes.inference.response_payload", exploding)

    # Still raised, never swallowed: the completion line is a record of the failure, not a handler for it.
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    outcomes = _request_outcomes(caplog.records)
    assert len(outcomes) == 1, "an exception on the way out is an exit path and owes exactly one line"
    line, status = outcomes[0]
    assert status == "fail"
    # The exception is named, not merely alluded to. `str(RuntimeError())` is empty and would leave the detail as a colon with nothing after it, so the line quotes the `repr` — which is why the class name appears here even though this one does have a message.
    assert "request failed before a response: RuntimeError" in line
    assert _registry(client).snapshot() == [], "and the slot is still released"


def test_a_client_that_hung_up_mid_body_is_reported_as_gone_rather_than_as_a_failure(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The other half of the same exit, and the reason it is not one branch.

    A client abandoning a turn is routine on a proxy fronting an interactive one; a reply this proxy could not parse is an incident. Reporting both as `[FAIL]` with one shared sentence would bury the second under the first, which is the ruling `_StreamAccounting._ending` already records for the streaming path.

    `Request.body` is patched because `TestClient` has no way to announce a body and then stop sending. What is being fixed is what `_serve` does with the exception, and that is exactly what arrives here — `ClientDisconnect`, unwrapped, nothing between the raise and the handler.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))

    async def body(self: Request) -> bytes:
        raise ClientDisconnect

    with caplog.at_level(logging.INFO), pytest.MonkeyPatch.context() as patch:
        patch.setattr(Request, "body", body)
        with pytest.raises(ClientDisconnect):
            client.post("/v1/messages", json={"model": "claude-model", "messages": []})

    outcomes = _request_outcomes(caplog.records)
    assert len(outcomes) == 1
    line, status = outcomes[0]
    assert status == "gone"
    # Asserted separately from the status, because `_add_status_prefix` renders an unrecognised one as `[....]` — a line that then merely looks unremarkable instead of failing.
    assert _request_prefixes(caplog.records) == ["[GONE]"]
    assert "client disconnected before the request was answered" in line
    assert _registry(client).snapshot() == []


def test_a_streaming_request_reports_what_it_actually_delivered(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    # Written by the delivery generator, not by the handler: at the moment the handler returns a stream has sent nothing, so a line written there would report every stream as having delivered zero bytes.
    client, _ = make_client(
        lambda _: httpx2.Response(
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


@pytest.mark.parametrize(
    ("failure", "drained", "expected_status", "expected_detail"),
    [
        pytest.param(
            ConnectionError("upstream tore"),
            False,
            "fail",
            "stream failed before a terminal event: upstream tore",
            id="upstream-tear",
        ),
        pytest.param(
            None,
            False,
            "gone",
            "delivery stopped before upstream finished",
            id="client-left",
        ),
        pytest.param(None, True, "ok", None, id="clean-drain"),
    ],
)
def test_one_shot_accounting_reports_how_delivery_actually_ended(
    request_log: None,
    caplog: pytest.LogCaptureFixture,
    failure: BaseException | None,
    drained: bool,
    expected_status: str,
    expected_detail: str | None,
) -> None:
    """A leg without an assembler still knows whether delivery tore, was abandoned, or drained cleanly.

    The assembler gate used to suppress this entire decision, making the first two rows indistinguishable from the clean control as `[ OK ] 200`.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "unused"}))
    chain = _chain_of(client)
    trace = RequestTrace(
        method="POST",
        path="/chat/completions",
        request_id="req-one-shot",
        started=time.monotonic(),
    )
    accounting = _StreamAccounting(
        chain=chain,
        request_id=trace.request_id,
        trace=trace,
        status_code=200,
        drained=drained,
        failure=failure,
    )
    chain.active_requests.add(trace.request_id)

    with caplog.at_level(logging.INFO):
        accounting.finish()

    (line, status), = _request_outcomes(caplog.records)
    assert status == expected_status
    if expected_detail is None:
        assert "stream failed before a terminal event" not in line
        assert "delivery stopped before upstream finished" not in line
    else:
        assert expected_detail in line


@pytest.mark.asyncio
async def test_a_client_deadline_is_accounted_as_the_failure_its_frame_reports(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Writing the deadline frame does not turn the deadline into a clean drain.

    The original exception must continue into `_tracked_delivery`, which is the layer that records the completion-line verdict.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "unused"}))
    chain = _chain_of(client)
    trace = RequestTrace(
        method="POST",
        path="/v1/messages",
        request_id="req-client-deadline",
        started=time.monotonic(),
    )
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain,
        request_id=trace.request_id,
        trace=trace,
        status_code=200,
        assembler=assembler,
    )
    chain.active_requests.add(trace.request_id)

    async def deadline_after_one_block() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        raise ClientDeadlineError("client request exceeded its deadline")

    delivery = _tracked_delivery(
        delivering(
            deadline_after_one_block(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        ),
        accounting,
    )
    chunks: list[bytes] = []

    with caplog.at_level(logging.INFO), pytest.raises(ClientDeadlineError):
        async for chunk in delivery:
            chunks.append(chunk)

    assert b"client_deadline_exceeded" in b"".join(chunks)
    (line, status), = _request_outcomes(caplog.records)
    assert status == "fail"
    assert "client request exceeded its deadline" in line
    assert "upstream stream ended without a terminal event" not in line


def test_a_stream_that_never_terminated_is_not_reported_as_a_clean_finish(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The reported line, in full: `[ OK ] 09:00:11 H1/H2 200 anthropic-messages/claude-opus-5 385.0s ↑583.5KB ↓43.2KB`.

    43KB had come back over 385 seconds and then upstream stopped without saying how the turn ended. The reply summary was gated on having seen that ending, so it was never taken onto the line — and every field that says what a reply *was* dropped out together, leaving something indistinguishable from a quiet successful request. The status could not correct it either: it is fixed when the response headers arrive and stays 200 however the stream ends.

    So the two halves are asserted separately. The prefix must say `fail`, and the line must name the truncation rather than leave it to be inferred from which fields are missing — an absence reads the same as a field this endpoint does not report.
    """
    client, _ = make_client(
        lambda _: httpx2.Response(
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = RequestTrace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain, request_id="req_1", trace=trace, status_code=200, assembler=assembler
    )
    chain.active_requests.add("req_1")

    async def tears_after_the_first_block() -> AsyncIterator[bytes]:
        whole = sse_upstream("first", "second")
        yield whole[: whole.index(b'event: content_block_start\ndata: {"index":1', 1)]
        raise httpx2.ReadError("connection reset by peer")

    delivery = _tracked_delivery(
        delivering(
            tears_after_the_first_block(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        ),
        accounting,
    )

    with caplog.at_level(logging.INFO):
        async with asyncio.timeout(10):
            assert await anext(delivery), "the first block should have reached the client"
            with pytest.raises(httpx2.ReadError):
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = RequestTrace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain, request_id="req_1", trace=trace, status_code=200, assembler=assembler
    )
    chain.active_requests.add("req_1")

    async def tears_after_its_stop_reason() -> AsyncIterator[bytes]:
        # Everything including `message_delta`, so upstream's reason is on the record, and then nothing.
        yield sse_upstream_without_message_stop("first", "second")
        raise httpx2.ReadError("connection reset by peer")

    delivery = _tracked_delivery(
        delivering(
            tears_after_its_stop_reason(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
        ),
        accounting,
    )

    with caplog.at_level(logging.INFO):
        async with asyncio.timeout(10):
            with pytest.raises(httpx2.ReadError):
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
        lambda _: httpx2.Response(
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))
    chain = _chain_of(client)
    trace = RequestTrace(method="POST", path="/v1/messages", request_id="req_1", started=time.monotonic())
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
        delivering(
            still_sending(),
            assembler,
            buffer=delivery_buffer(chain),
            settings=stream_settings(chain),
            framer=AnthropicFramer(message_id="msg_1", model="claude-model"),
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
        lambda _: httpx2.Response(
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
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}))

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
        lambda _: httpx2.Response(200, json={"input_tokens": 4242}), mappings={"alias": "claude-model"}
    )

    with caplog.at_level(logging.INFO):
        client.post("/v1/messages/count_tokens", json={"model": "alias", "messages": [{"role": "user", "content": "hi"}]})

    line = _request_lines(caplog.records)[0]
    assert "alias → claude-model" in line
    assert "↑4.2k" in line


def test_upstream_token_usage_reaches_the_line(request_log: None, caplog: pytest.LogCaptureFixture) -> None:
    # Taken from the payload that goes downstream, so the numbers on the line are the ones the client was told.
    client, _ = make_client(
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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

    Hand-written because what it has to hold up is the route → assembler → line wiring under an event contract that is already known, not how Copilot actually behaves on the wire. The frames only have to be shaped enough for the assembler to open and close both items. Anything asserting the real upstream's quirks — id instability, chunk boundaries — belongs on a cassette instead; see `tests/int/recorded/`.
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


def test_a_direct_responses_stream_is_answered_in_responses_events() -> None:
    """A client that asked on `/responses` gets `response.*`, not Anthropic event names.

    Until 2026-08-22 it got the Anthropic ones: delivery had a single outbound framer and used it whatever the client had asked in. `assembler_for` was already choosing correctly for the upstream leg, which is the half that made this easy to miss — the stream parsed fine and came out in the wrong protocol.

    Asserted on the event names because that is the part a client dispatches on, and on the absence of the Anthropic ones because "also emits" would be just as broken as "emits instead".
    """
    client, seen = make_client(
        lambda _: httpx2.Response(
            200,
            content=responses_sse_upstream(),
            headers={"content-type": "text/event-stream"},
        )
    )
    response = client.post(
        "/responses",
        json={"model": "gpt-model", "input": [], "stream": True},
    )

    assert response.status_code == 200
    assert str(seen[-1].url) == f"{BASE_URL}/responses"
    names = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert names[0] == "response.created"
    assert names[-1] == "response.completed"
    assert "response.output_item.done" in names
    assert not [name for name in names if name.startswith(("message_", "content_block_"))]


def test_an_anthropic_client_on_a_responses_upstream_still_gets_anthropic_events() -> None:
    """The other half of the same decision, and the one that would break the main product path.

    This route is assembled by the Responses assembler because that is what answered, and framed by the Anthropic framer because that is what the client asked in. Selecting the framer by the upstream's dialect would send `response.*` to Claude Code.
    """
    client, _ = make_client(
        lambda _: httpx2.Response(
            200,
            content=responses_sse_upstream(),
            headers={"content-type": "text/event-stream"},
        )
    )
    response = client.post(
        "/v1/messages",
        json={"model": "gpt-model", "messages": [], "stream": True},
    )

    assert response.status_code == 200
    names = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert names[0] == "message_start"
    assert names[-1] == "message_stop"
    assert not [name for name in names if name.startswith("response.")]


def test_a_streamed_responses_reply_is_logged_in_its_own_words(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The streaming half of the same wording decision.

    Its dialect comes from the assembler that read the stream rather than from the route, so the two paths reach the same answer by different routes and both have to be held to it.
    """
    client, _ = make_client(
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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

    Responses counts the cached portion inside `input_tokens` and puts the breakdown in `input_tokens_details`. Copied across untouched, the client got keys it has no schema for, no `cache_read_input_tokens` at all, and an `input_tokens` meaning the opposite of what Anthropic's means — a cached prompt arriving downstream as a full-price one. The streaming path converts, so the same route was answering with two different usage contracts depending on one flag.
    """
    client, _ = make_client(
        lambda _: httpx2.Response(
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
        lambda _: httpx2.Response(
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


def _upstream_that_goes_quiet(gap: float) -> Callable[[httpx2.Request], httpx2.Response]:
    """One whole block, then a silence longer than any guard under test, then the rest."""
    whole = sse_upstream("first")
    head, _, tail = whole.partition(b'event: message_delta')

    def handler(_: httpx2.Request) -> httpx2.Response:
        async def body() -> AsyncIterator[bytes]:
            yield head
            await asyncio.sleep(gap)
            yield b'event: message_delta' + tail

        return httpx2.Response(200, content=body(), headers={"content-type": "text/event-stream"})

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

    # Given up on the same way every other mid-stream upstream failure is. What that looks like to the client is not this guard's to answer: a timeout is continuable and this upstream delivers a whole block before going quiet, so the turn is handed back as a tool call rather than torn off.
    # The silence is 1.5s against a 1s guard, so a guard that never fired would run the full gap and then deliver upstream's own ending.
    started = time.monotonic()
    delivered = _delivered(client)
    elapsed = time.monotonic() - started

    assert elapsed < 1.4, f"the idle guard never fired: {elapsed:.1f}s"
    assert b"turn_interrupted" in delivered
    # What the client had already been given is still there.
    assert b'"text":"first"' in delivered


def test_the_bundled_default_leaves_a_quiet_upstream_alone() -> None:
    # 0 is the bundled default and it disables the guard. The frozen invariant is never to false-kill legitimate thinking, so a turn that goes quiet for longer than any timeout would have allowed must still be delivered whole when nobody asked for one.
    client, _ = make_client(_upstream_that_goes_quiet(1.5))

    delivered = _delivered(client)

    assert b'"text":"first"' in delivered
    assert b"message_stop" in delivered



def _upstream_that_trickles(rounds: int) -> Callable[[httpx2.Request], httpx2.Response]:
    """Never silent, and far too slow to finish: the shape neither phase guard can see.

    Ends on its own after `rounds`, so that a deadline which failed to fire shows up as a stream that ran to completion rather than as a test that never returns.
    """
    whole = sse_upstream("first")
    head, _, tail = whole.partition(b"event: message_delta")

    def handler(_: httpx2.Request) -> httpx2.Response:
        async def body() -> AsyncIterator[bytes]:
            yield head
            for _round in range(rounds):
                await asyncio.sleep(0.05)
                yield b": ping\n\n"
            yield b"event: message_delta" + tail

        return httpx2.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    return handler


def test_the_attempt_deadline_reaches_the_streamed_body() -> None:
    """The deadline was enforced only up to the response headers, because that is where the driver's await ends on a streaming request. Everything after — the part the setting's own documentation says it exists for — ran unbounded.

    Asserted on when the turn ends rather than on it raising. A timeout is a continuable failure and this upstream delivers a whole block before it starts trickling, so the turn is handed back to the client as a tool call instead of being torn off. Sixty rounds of 0.05s is three seconds of trickle against a one-second deadline: a deadline that did not reach the body would run all three.
    """
    client, _ = make_client(
        _upstream_that_trickles(rounds=60),
        overrides={"upstream_request_timeouts": {"upstream_request_deadline": 1}},
    )

    started = time.monotonic()
    delivered = _delivered(client)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"the deadline never reached the body: {elapsed:.1f}s"
    assert b"turn_interrupted" in delivered


def _upstream_slow_to_answer(delay: float) -> Callable[[httpx2.Request], Any]:
    async def handler(_: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(delay)
        return httpx2.Response(
            200,
            content=sse_upstream("first"),
            headers={"content-type": "text/event-stream"},
        )

    return handler


def test_the_configured_header_timeout_reaches_the_driver() -> None:
    # The wire from the config file to the guard, which is the part that had been missing entirely: `response_header` was read, validated, and then handed to nothing. A guard that exists but is never given its setting looks exactly like one set generously, and the only way to tell them apart is to configure it and watch it fire.
    client, _ = make_client(
        _upstream_slow_to_answer(1.5),
        overrides={"upstream_request_timeouts": {"response_header": 1}},
    )

    response = client.post(
        "/v1/messages", json={"model": "claude-model", "messages": [], "stream": True}
    )

    assert response.status_code != 200
    assert "no response headers within 1s" in response.text


def test_a_slow_answer_is_left_alone_when_no_header_timeout_is_set() -> None:
    # 0 is the bundled default, and the other direction has to hold too: the guard must not be firing on its own account.
    client, _ = make_client(_upstream_slow_to_answer(1.5))

    assert b'"text":"first"' in _delivered(client)


def _upstream_slow_then_trickling(header_delay: float, rounds: int) -> Callable[[httpx2.Request], Any]:
    whole = sse_upstream("first")
    head, _, tail = whole.partition(b"event: message_delta")

    async def handler(_: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(header_delay)

        async def body() -> AsyncIterator[bytes]:
            yield head
            for _round in range(rounds):
                await asyncio.sleep(0.05)
                yield b": ping\n\n"
            yield b"event: message_delta" + tail

        return httpx2.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    return handler


def test_the_deadline_is_one_instant_and_not_a_duration_started_twice() -> None:
    # The driver fixes the instant and the delivery chain reads it. Were the delivery chain to work it out again from its own clock, it would start counting when the headers arrived — and an attempt that spent two seconds waiting for them would get its full life all over again on top.
    # Measured rather than asserted structurally, because the two readings differ only in when they land: three seconds from the start of the attempt, or three more from the moment the headers came back.
    client, _ = make_client(
        _upstream_slow_then_trickling(header_delay=2.0, rounds=200),
        overrides={"upstream_request_timeouts": {"upstream_request_deadline": 3}},
    )

    started = time.monotonic()
    delivered = _delivered(client)
    elapsed = time.monotonic() - started

    # The headers alone cost two of the three seconds. Recomputing downstream would land near five.
    assert elapsed < 4.0, f"the deadline was restarted downstream: {elapsed:.1f}s"
    # Ended by handing the turn back, not by tearing it off: a timeout is continuable and a whole block had already gone out.
    assert b"turn_interrupted" in delivered


def _records() -> list[dict[str, Any]]:
    """Every structured request record written so far, in order.

    Reads the file the app actually wrote rather than intercepting the call, so a record that never reached disk fails here. `tests/int/conftest.py` points the data home at a temporary directory.
    """
    files = sorted(request_logs_dir().glob("requests-*.jsonl"))
    return [cast(dict[str, Any], orjson.loads(line)) for path in files for line in path.read_text().splitlines()]


def test_a_translated_request_records_what_it_could_not_carry() -> None:
    """The losses translation collects reach the record, instead of stopping at `context.extras`.

    `Conversion` has always recorded these and `LossCode` was written so a metric could key on them, but nothing read either: a request whose `top_p` and `stop_sequences` never crossed produced the same record, the same console line and the same reply as one that crossed intact. So this asserts the whole way through — an inbound field nothing claims, translated to a format that cannot take it, named in the record on the way out.

    Asserted on the detail as well as the code because the code alone cannot say *which* fields were dropped, and "something was lost" is not actionable.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
            # Neither is modelled by `SemanticRequest`, so both land in `extensions` and are dropped at the format boundary.
            "top_p": 0.5,
            "stop_sequences": ["STOP"],
        },
    )
    assert response.status_code == 200

    records = _records()
    assert len(records) == 1, records
    losses = records[0]["losses"]
    assert [entry["direction"] for entry in losses] == ["request"]
    assert [entry["code"] for entry in losses] == ["extensions-not-carried"]
    detail = losses[0]["detail"]
    assert "top_p" in detail and "stop_sequences" in detail, detail


def test_a_translated_request_that_lost_nothing_records_nothing() -> None:
    """A crossing that *could* have lost something and did not.

    An earlier version used `claude-model`, which is served untranslated — so it proved only that a request with no translator records no losses, which is true of an implementation that reports a loss on every translation. `gpt-model` is translated; this body simply has nothing in it that the Responses format cannot take.
    """
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
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

    records = _records()
    assert len(records) == 1, records
    assert records[0]["losses"] == [], records[0]["losses"]


def test_a_recorded_loss_is_also_counted() -> None:
    """The counter and the record are produced from one tuple, so `/metrics` cannot disagree with the file.

    A counter defined but never incremented is this repository's most common defect shape — a configuration surface with no consumer — so the increment is asserted rather than assumed from the fact that the line exists.
    """
    labels = {"direction": "request", "code": "extensions-not-carried"}
    before = REGISTRY.get_sample_value("ghc_proxy_translation_losses_total", labels) or 0.0

    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={"model": "gpt-model", "messages": [{"role": "user", "content": "hi"}], "top_p": 0.5},
    )
    assert response.status_code == 200

    after = REGISTRY.get_sample_value("ghc_proxy_translation_losses_total", labels) or 0.0
    assert after == before + 1


ATTRIBUTION_LINE = "x-anthropic-billing-header: cc_version=1.0; cc_entrypoint=cli;"
# The strip is off unless asked for, so every test that wants it has to say so — which is itself the assertion that the switch is read.
OVERRIDES_STRIP_ATTRIBUTION = {"hook_strip_anthropic_request_headers": {"strip_attribution_header": True}}


def test_the_attribution_line_survives_when_the_operator_has_not_asked() -> None:
    """Off by default, per `message-format-reshape.md`. Upstream accepts the line, so leaving it costs tokens rather than correctness — and a strip nobody switched on must not happen."""
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": [{"type": "text", "text": f"{ATTRIBUTION_LINE}\nBe brief."}],
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    assert "x-anthropic-billing-header" in seen[-1].read().decode()


def test_the_attribution_line_never_reaches_a_translated_upstream() -> None:
    """Asserted on the bytes that left, not on the function that removes it.

    A unit test proves the stripper works; it cannot prove anything calls it. This repository's most common defect is a capability that exists and is never wired — so the check that matters is made against the request upstream actually received.
    """
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "resp_1"}),
        overrides=OVERRIDES_STRIP_ATTRIBUTION,
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "system": [{"type": "text", "text": f"{ATTRIBUTION_LINE}\nBe brief."}],
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    sent = seen[-1].read().decode()
    assert "x-anthropic-billing-header" not in sent
    assert "Be brief." in sent


def test_the_attribution_line_never_reaches_a_direct_upstream() -> None:
    """The untranslated leg carries `system` through untouched, so the removal has to happen before the routing decision rather than inside either translator."""
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"id": "msg_1", "content": []}),
        overrides=OVERRIDES_STRIP_ATTRIBUTION,
    )
    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-model",
            "system": [{"type": "text", "text": f"{ATTRIBUTION_LINE}\nBe brief."}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 200
    sent = seen[-1].read().decode()
    assert "x-anthropic-billing-header" not in sent
    assert "Be brief." in sent


def test_the_attribution_line_is_not_counted_as_prompt() -> None:
    """`count_tokens` is named alongside `/v1/messages` in `message-format-reshape.md`, and it is the endpoint where leaving the line in is measurable: upstream counted the same prompt at 43 tokens without it and 77 with it."""
    client, seen = make_client(
        lambda _: httpx2.Response(200, json={"input_tokens": 11}),
        overrides=OVERRIDES_STRIP_ATTRIBUTION,
    )
    response = client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "claude-model",
            "system": [{"type": "text", "text": f"{ATTRIBUTION_LINE}\nBe brief."}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 200
    sent = seen[-1].read().decode()
    assert "x-anthropic-billing-header" not in sent
    assert "Be brief." in sent


def test_a_thinking_budget_reaches_upstream_as_an_effort_the_model_offers() -> None:
    """The whole channel: an Anthropic `thinking` budget, through routing, to the bytes upstream received.

    Before this existed the field was dropped at the format boundary and `EXTENSIONS_NOT_CARRIED` was the only trace — so a client asking for deep reasoning got whatever the upstream defaulted to, and nothing said so.

    32k asks for `max`. This model publishes only low/medium/high, so `high` is the honest answer and `max` would be a 400.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "reasoning-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
            "thinking": {"type": "enabled", "budget_tokens": 32_000},
        },
    )

    assert response.status_code == 200
    sent = cast(dict[str, Any], orjson.loads(seen[-1].read()))
    assert sent["reasoning"] == {"effort": "high"}


def test_a_model_that_publishes_no_efforts_is_sent_none_rather_than_a_guess() -> None:
    """`gpt-model` has no `capabilities` in the catalog at all. Inventing an effort for it would be asking for something upstream never said it takes; the request goes without one and the record says why."""
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 32_000},
        },
    )

    assert response.status_code == 200
    sent = cast(dict[str, Any], orjson.loads(seen[-1].read()))
    assert "reasoning" not in sent

    codes = [entry["code"] for entry in _records()[0]["losses"]]
    assert "reasoning-intent-not-carried" in codes


def test_an_approximated_effort_is_recorded_as_a_loss() -> None:
    """Downgrading `max` to `high` changes what the client asked for, so it is reported rather than done quietly."""
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "reasoning-model",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 32_000},
        },
    )

    assert response.status_code == 200
    losses = _records()[0]["losses"]
    approximations = [entry for entry in losses if entry["code"] == "reasoning-intent-approximated"]
    assert len(approximations) == 1
    assert "max" in approximations[0]["detail"] and "high" in approximations[0]["detail"]


def test_an_unreadable_thinking_field_is_refused_by_name() -> None:
    """A client error rather than a silent approximation: nothing can be chosen for a budget of `-1`, and guessing would send an effort the request never asked for."""
    client, _ = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
    response = client.post(
        "/v1/messages",
        json={
            "model": "reasoning-model",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": -1},
        },
    )

    assert response.status_code == 400
    # `param` rather than `field_path`: the field that names which part of the request is at fault now uses the spelling OpenAI declares and Anthropic tolerates, instead of one only this project used.
    assert response.json()["error"]["param"] == "thinking.budget_tokens"


def test_a_count_resolves_reasoning_the_same_way_the_send_does() -> None:
    """Counting measures the body that would be sent, so it has to resolve `thinking` the same way.

    Nothing goes upstream on this path — the Responses family has no counter — so the resolution cannot be read off a request. It is read off the loss the resolution recorded instead, which is the only observable this path produces. Asserting merely that the count came back and that nothing was sent is what the first version of this test did, and it stayed green with the capability channel removed from `handle_count_tokens` entirely.
    """
    client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1", "usage": {"input_tokens": 7}}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "reasoning-model",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 32_000},
        },
    )

    assert response.status_code == 200
    assert response.json()["estimated"] is True
    assert not [request for request in seen if "reasoning" in request.read().decode()]

    # 20k wants `xhigh`; this model stops at `high`. The count path saw the same capabilities and made the same downgrade — with the channel disconnected it reports `not-carried` instead.
    losses = _records()[0]["losses"]
    approximations = [entry for entry in losses if entry["code"] == "reasoning-intent-approximated"]
    assert len(approximations) == 1, losses
    assert "max" in approximations[0]["detail"] and "high" in approximations[0]["detail"]


def test_a_silence_in_the_middle_of_a_delivered_stream_reaches_the_record() -> None:
    """The pacing numbers have to arrive on the record by the path a streamed request actually takes.

    What they mean is pinned where they are taken, in `tests/unit/pipeline/delivery/test_stream_delivery.py`; what this adds is that `_counted_upstream` is still the layer production streams through and that both fields survive the trace, the line and the writer. A field added to `RequestLine` and never assigned from the trace is written on every request as its default, which reads exactly like a stream nobody had to wait for.
    """
    quiet = 0.4
    client, _ = make_client(_upstream_that_goes_quiet(quiet))

    assert _delivered(client), "this test is only meaningful if the stream was delivered"

    records = _records()
    assert len(records) == 1, records
    assert records[0]["upstream_chunks"] >= 2, "a stream that arrived in one piece cannot have a gap in it"
    assert cast(float, records[0]["upstream_max_gap_s"]) >= quiet


def test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end() -> None:
    """The whole point of the traceless retry, asserted through the real app rather than the seam.

    The first attempt opens a block and the connection dies before it closes, so nothing was ever delivered — the preamble travels with the first complete block, which is what makes "the client has seen bytes" and "a block was delivered" the same fact. A second attempt answers the same request and the client cannot tell there were two: one `message_start`, one message, and none of the first attempt's text in it.

    Asserted on upstream being asked twice as well, because a version that simply swallowed the tear and returned the second attempt's bytes would look identical on the wire without ever having replayed anything.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200,
            content=sse_upstream("kept"),
            headers={"content-type": "text/event-stream"},
        )

    client, _ = make_client(upstream)
    response = client.post(
        "/v1/messages",
        json={"model": "claude-model", "messages": [], "stream": True},
    )

    assert response.status_code == 200
    events = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert events.count("message_start") == 1
    assert events[-1] == "message_stop"
    assert "kept" in response.text
    assert len(calls) == 2


def test_a_replay_on_the_translation_leg_sends_the_conversation_again() -> None:
    """The primary path, where a replayed attempt has to send what the *client* sent.

    `handle` translates in place — it assigns the translated body back onto the context and edits the dict it was given — so a second pass over the same context translated an already-translated body. Measured before the fix: the second attempt went out as `{"model": "gpt-model", "input": [], "stream": true}`, and the client was answered from an empty prompt with a clean 200. The earlier end-to-end replay test uses `claude-model`, which needs no translation, so it was structurally unable to see this.

    Asserted on the second request's bytes rather than on the reply, because that reply looked entirely healthy.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: response.output_item.added\n'
            b'data: {"output_index":0,"item":{"type":"reasoning","id":"rs_1","summary":[],'
            b'"encrypted_content":"sealed"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200,
            content=responses_sse_upstream(),
            headers={"content-type": "text/event-stream"},
        )

    client, seen = make_client(upstream)
    response = client.post(
        "/v1/messages",
        json={
            "model": "gpt-model",
            "messages": [{"role": "user", "content": "remember me"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert len(calls) == 2
    replayed = orjson.loads(seen[-1].content)
    # The conversation is still there. An empty `input` is the whole defect.
    assert replayed["input"], replayed
    assert "remember me" in seen[-1].content.decode()
    # And it was translated exactly once: a second pass would have wrapped the Responses body again.
    assert "messages" not in replayed


def test_a_replay_is_reported_on_the_request_line(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A request the proxy quietly answered twice must not read like one it answered once.

    The attempt count is the one surface that can show it, and the handler writes it when it returns — which for a streaming request is before any replay has happened. Refreshed by the reopen for that reason.

    Read off the record the app actually wrote, so a count that never reached disk fails here.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200,
            content=sse_upstream("kept"),
            headers={"content-type": "text/event-stream"},
        )

    client, _ = make_client(upstream)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages",
            json={"model": "claude-model", "messages": [], "stream": True},
        )

    assert response.status_code == 200
    assert len(calls) == 2
    record = _records()[-1]
    assert record["attempts"] == 2
    # And what it replaced. A transparent replay that succeeds neither hands over nor re-raises, so `attempts` was the whole account and the exception that caused it was gone — invisible to the client by design, invisible to the record by accident.
    replaced = cast(list[str], record["replaced_failures"])
    assert len(replaced) == 1
    assert "RemoteProtocolError" in replaced[0]
    assert "peer closed the connection" in replaced[0]
    # And on the line this test is named for. A review deleted the rendering branch and every test here stayed green, because they all read the structured record instead.
    line = next(item for item in _request_lines(caplog.records) if "retries=" in item)
    assert "RemoteProtocolError" in line
    assert "peer closed the connection" in line


def test_a_tear_after_the_turn_finished_is_recorded_without_being_called_a_failure(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The one ending that discarded its exception and left no trace of it anywhere.

    Upstream sends its terminal event and *then* the connection goes. The client is owed nothing more, so delivery breaks out of its loop, writes the terminal frames and returns cleanly — and `torn` was dropped where it was caught. The request was accounted a plain success, which it is, with nothing to say a peer had just reset the connection under it.

    Found while a review refuted a claim that the hand-over was the only ending that swallowed its cause. It was the second, and the worse of the two: the hand-over at least had a field to be read from.

    `ok`, deliberately. Painting this red would put a turn nothing went wrong with beside the ones that failed, and the whole point of the status column is that the two look different.
    """
    calls: list[int] = []

    async def finishes_then_breaks() -> AsyncIterator[bytes]:
        # One block, not one byte at a time: `sse_upstream` returns the whole stream as `bytes`, and iterating that yields ints.
        yield sse_upstream("done")
        # Everything the client was owed has been delivered; only the socket is left.
        raise httpx2.RemoteProtocolError("peer reset the connection after its last frame")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(
            200, content=finishes_then_breaks(), headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(upstream)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/v1/messages",
            json={"model": "claude-model", "messages": [], "stream": True},
        )

    assert response.status_code == 200
    assert "message_stop" in response.text, "the premise: the client got the whole turn"
    assert calls == [1], "and nothing was replayed — there was nothing left to replay"

    record = _records()[-1]
    # Its own field rather than `detail`: `detail` says how the turn came out, and this says what the connection did afterwards. They are not alternatives — see the `max_tokens` case above, where both are set.
    assert "RemoteProtocolError" in record["tore_after_terminal"]
    assert "peer reset the connection after its last frame" in record["tore_after_terminal"]
    assert record["detail"] == "", "nothing went wrong with the turn itself"
    # Matched on the note, not on the route: a line that succeeded names the model instead, which is what this one does.
    line = next(item for item in _request_lines(caplog.records) if "closed abruptly" in item)
    assert "RemoteProtocolError" in line
    # Not painted as a failure: the turn is complete and the client has it.
    assert record["status"] == "ok"
    assert "end_turn" in line


def test_a_replacement_that_never_opened_an_attempt_is_not_recorded_as_one(
    request_log: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry and the attempt count are written off the same fact, so neither can appear without the other.

    `context.attempt_count` advances in `RequestContext.begin_attempt`, which `DirectDriver.run` calls on the way in, and `handle` can fail well before reaching it — `shape_request` and translation both run first. Recording the replacement on the way in was the fix for losing a replacement that failed *after* opening its attempt, and it overshot in the other direction: measured, one upstream call, `attempts=1`, and a `replaced_failures` entry for a replay that had not opened one.

    **"Opened an attempt", not "reached upstream" — a review narrowed this and the distinction is real.** `begin_attempt` runs before the prepare subscribers, before the rate limiter and before `_send`, so a replacement that fails between them advances the count with no upstream I/O and *is* recorded. The injection point below sits in `shape_request`, which satisfies both readings, so this test cannot tell them apart and does not claim to. If "a byte actually left" is ever the fact wanted, `attempt_count` is the wrong oracle for it and a new one belongs at the provider-send boundary — that is a product question, not something a test's wording should settle quietly.

    A phantom here is worse than a missing entry, because the field exists to answer "what did this proxy quietly do" and an invented answer is unfalsifiable from the record.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        )

    real_shape = driver.shape_request
    shaped: list[int] = []

    def shape_once(*args: Any, **kwargs: Any) -> Any:
        shaped.append(1)
        if len(shaped) > 1:
            # Before the driver exists, let alone `begin_attempt` — the same position a routing or translation failure occupies.
            raise RuntimeError("the replay could not even be shaped")
        return real_shape(*args, **kwargs)

    monkeypatch.setattr(driver, "shape_request", shape_once)

    client, _ = make_client(upstream)
    with contextlib.suppress(Exception):
        client.post("/v1/messages", json={"model": "claude-model", "messages": [], "stream": True})

    assert len(shaped) == 2, "the premise: a replay was attempted"
    assert calls == [1], "and it failed before the driver could open an attempt for it"
    record = _records()[-1]
    assert record["attempts"] == 1
    assert record["replaced_failures"] == []


def test_a_long_upstream_failure_is_cut_before_it_reaches_the_line(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The bound has to hold from `_reopen` all the way to the rendered line, not just in the helper.

    `one_line` has its own tests and this path has its own tests, and a review cut the production call back to a bare `repr` with both sides staying green — the seam between them was what nothing crossed. Upstream chooses this text, `repr` has no limit, and the completion line is one line.
    """
    calls: list[int] = []
    huge = "x" * 10_000

    async def torn_body() -> AsyncIterator[bytes]:
        # Opened but nothing completed, so the ending is a transparent replay rather than a hand-over — the two put a cause on the line through different fields, and this one is about the replay.
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError(huge)

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx2.Response(
                200, content=torn_body(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(
            200, content=sse_upstream("kept"), headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(upstream)
    with caplog.at_level(logging.INFO):
        _delivered(client)

    replaced = cast(list[str], _records()[-1]["replaced_failures"])
    assert len(replaced) == 1
    # Cut, and saying so rather than trailing off — the same shape the hand-over message uses.
    assert len(replaced[0]) < 400
    assert "more chars" in replaced[0]
    line = next(item for item in _request_lines(caplog.records) if "retries=" in item)
    assert len(line) < 800
    assert huge not in line


def test_a_long_failure_is_cut_on_the_hand_over_line_too(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Two endings put an exception on this line, through two fields, and only one of them was bounded.

    Found by the replay test above: written first against a hand-over scenario by mistake, it printed ten thousand characters of upstream's own text on the completion line. `repr` has no limit of its own and the text is upstream's to choose, so the cut belongs at both.
    """
    huge = "y" * 10_000

    async def torn_body() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        raise httpx2.RemoteProtocolError(huge)

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    with caplog.at_level(logging.INFO):
        _delivered(client)

    line = next(item for item in _request_lines(caplog.records) if "handed back" in item)
    assert "RemoteProtocolError" in line
    assert "more chars" in line
    assert huge not in line
    assert len(line) < 800


def test_the_client_deadline_survives_a_replay() -> None:
    """The guard the first attempt was wrapped in goes out with the stream it was wrapping.

    Delivery swaps the byte stream when it replaces a torn attempt, so a replacement that is not wrapped again is bounded only by its own attempt's deadline. Measured before the fix: a two-second client deadline let a replayed body run for six.

    The upstream deadline is left far above the client one, so what stops this can only be the client's.

    The deadline now propagates after writing its error frame so accounting can see the same failure. The frame itself is pinned by the delivery tests; this test keeps its original subject, whether the replacement attempt is still bounded by the client's one clock.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    async def endless_body() -> AsyncIterator[bytes]:
        while True:
            await asyncio.sleep(0.05)
            yield b": ping\n\n"

    def upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        content = torn_body() if len(calls) == 1 else endless_body()
        return httpx2.Response(
            200, content=content, headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(
        upstream,
        overrides={
            "client_delivery": {"client_request_deadline": 2},
            "upstream_request_timeouts": {"upstream_request_deadline": 60},
        },
    )

    started = time.monotonic()
    with pytest.raises(ClientDeadlineError, match="client request exceeded its deadline"):
        client.post(
            "/v1/messages",
            json={"model": "claude-model", "messages": [], "stream": True},
        )
    elapsed = time.monotonic() - started

    assert calls == [1, 1], "the torn attempt was not replaced"
    assert elapsed < 5.0, f"the replayed body outlived the client deadline: {elapsed:.1f}s"


TOOL_NAME = "mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted"


def _handed_back(delivered: bytes) -> dict[str, Any]:
    """The synthesised tool call, reassembled from the frames it went out as."""
    text = delivered.decode()
    start = next(
        orjson.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ") and '"tool_use"' in line and '"content_block_start"' in line
    )
    partial = "".join(
        orjson.loads(line.removeprefix("data: "))["delta"]["partial_json"]
        for line in text.splitlines()
        if line.startswith("data: ") and '"input_json_delta"' in line
    )
    block = cast(dict[str, Any], start["content_block"])
    return {"name": block["name"], "id": block["id"], "input": orjson.loads(partial)}


def test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The client holds content this side cannot take back, so the turn is handed over rather than torn off.

    It goes out as a tool call because that is the one shape a client acts on by itself: it executes the tool, gets an instruction back, and asks again — carrying the turn on from its own transcript, which is the thing the proxy no longer has to reconstruct.
    """

    async def torn_body() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        # Assembled the way the installed stack assembles a real tear: httpcore raises `RemoteProtocolError(event)` holding the h2 event object, and httpx re-raises its text `from` that. This fixture used to raise a hand-built exception with a message and no cause, and a review showed that a formatter which never walked the chain — no cause, no HTTP/2 gloss, no request id — satisfied every assertion below.
        event = h2.events.ConnectionTerminated()
        event.error_code = h2.errors.ErrorCodes.NO_ERROR
        event.last_stream_id = 2147483647
        try:
            raise httpcore2.RemoteProtocolError(event)
        except httpcore2.RemoteProtocolError as from_core:
            raise httpx2.RemoteProtocolError(str(from_core)) from from_core

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    with caplog.at_level(logging.WARNING):
        delivered = _delivered(client)

    handed = _handed_back(delivered)
    assert handed["name"] == TOOL_NAME
    assert handed["id"].startswith("toolu_")
    assert handed["input"]["category"] == "network"
    assert handed["input"]["num_messages"] == 0
    # The client never declared the tool, which is said out loud rather than enforced.
    warned = [record.getMessage() for record in caplog.records if "auto_retry_tool_not_declared" in record.getMessage()]
    assert warned
    # Through the real wiring, not just the formatter. `interruption_message` has its own unit tests and they all stayed green through two separate cuts of this call site — first back to `str(error)`, then to a hand-rolled type-and-text string. What is pinned here is that the block the client receives carries the three things only the real formatter produces: the type it arrived as, the HTTP/2 error code decoded off the event one link down, and a request id that matches the one the proxy logged for this same turn.
    message = cast(str, handed["input"]["message"])
    assert "httpx2.RemoteProtocolError" in message
    assert "NO_ERROR" in message
    carried = re.search(r"\[request ([0-9a-f-]{36}), attempt (\d+)\]", message)
    assert carried is not None
    # Cross-checked against a value this side produced independently, so a literal cannot satisfy it.
    assert carried.group(1) in warned[0]
    assert carried.group(2) == "1"
    # A whole message, ending the way a turn that asks for a tool ends.
    assert b'"stop_reason":"tool_use"' in delivered
    assert b"message_stop" in delivered
    # And what the client kept is still there: the hand-over adds an ending, it does not replace one.
    assert b'"text":"first"' in delivered


def test_the_marker_sits_below_this_sides_bookkeeping_in_production(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Where the attribution marker is placed is a fact about `inference.py`, and only the served path can show it.

    The unit test beside `_counted_upstream` composes its own layers, so it proves the predicate and not the wiring — the shape this project has been bitten by twice. Here the registry the real `_counted_upstream` calls is replaced with one that raises after a block has gone out, so the failure originates *between* the marker and the client.

    Two reviews measured the wrong placement: with the marker around the whole composite, this bug was tagged as upstream's, handed to the client as a `tool_use`, and the delivery returned cleanly with the exception gone. What it must do instead is reach the caller.
    """

    class Exploding(ActiveRequestRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.seen = 0

        def add_bytes(self, request_id: str, count: int) -> None:
            self.seen += 1
            if self.seen >= 4:
                raise LookupError("bug in this side's byte counter")
            super().add_bytes(request_id, count)

    async def frame_by_frame() -> AsyncIterator[bytes]:
        # One chunk per frame, so the counter is called several times and the bug lands after a block has already gone out.
        for frame in sse_upstream("first", "second").split(b"\n\n"):
            if frame:
                yield frame + b"\n\n"

    client, _ = make_client(
        lambda _: httpx2.Response(
            200,
            content=frame_by_frame(),
            headers={"content-type": "text/event-stream"},
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    chain = _chain_of(client)
    setattr(cast(FastAPI, client.app).state, CHAIN_STATE_KEY, replace(chain, active_requests=Exploding()))

    with caplog.at_level(logging.INFO), pytest.raises(LookupError):
        _delivered(client)

    # And it is not dressed up as a turn the client can carry on from.
    assert not any("handed back" in line for line in _request_lines(caplog.records))


def test_a_hand_over_says_what_it_swallowed(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A hand-over is the one ending whose cause has nowhere else to go.

    It does not re-raise: the exception stops inside the delivery generator, so the accounting's `failure` — set from what propagates — stays `None`, and the completion line said only that a turn had been handed back. Every other ending on this path quotes its cause for exactly this reason, and two reviews found failures reaching the client through this one with no account of them anywhere.
    """

    async def torn_body() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    with caplog.at_level(logging.INFO):
        _delivered(client)

    handed_lines = [line for line in _request_lines(caplog.records) if "handed back" in line]
    assert len(handed_lines) == 1
    assert "RemoteProtocolError" in handed_lines[0]
    assert "peer closed the connection" in handed_lines[0]


def test_a_failure_the_taxonomy_cannot_name_is_still_upstreams() -> None:
    """The hand-over used to call an unnameable failure `internal`, which says the proxy broke.

    Whether the retry taxonomy has a word for a failure and whose failure it was are different questions, and only the first has a table here. The second is already answered by the gate that lets a hand-over happen at all: `stream.py` reaches one only on `not ours`, having positively identified this side's own protections and anything raised out of its own code.

    `httpx2.DecodingError` is the carrier because it is real — nine call sites in `httpx2/_decoders.py`, raised when upstream's compressed body will not decompress — and because `normalize_upstream_error` genuinely cannot name it: it descends from `RequestError`, not `TransportError`. `deferred.md` §22.
    """

    async def torn_body() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        raise httpx2.DecodingError("Error -3 while decompressing data")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    handed = _handed_back(_delivered(client))

    assert handed["input"]["category"] == "upstream"
    assert "DecodingError" in cast(str, handed["input"]["message"])


def test_a_draining_process_does_not_replay_a_stream_the_client_never_saw() -> None:
    """A replay opens a new upstream attempt, and a process that has stopped accepting has promised not to take work on.

    Deliberately the *same* scenario as `test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end` — nothing delivered, a mid-block tear, budget at its default — so the only difference is that the drain began while the request was in flight. That test measures two upstream calls; this one measures one. Neither number means anything without the other.

    The drain is begun from inside the upstream handler because that is when it happens in production: a drain waits for the requests already running, so the ones it has to stop are exactly the ones already past this point.

    **What the client gets is the truncated ending, not a hand-over**, and asserting that is the point rather than an omission. It is not that a hand-over is impossible here — `_hand_over` builds its own preamble when nothing has started — but that its `committed_count == 0` gate does not let this case through. Whether it should is open; see `deferred.md` §5. An earlier version of this test used a scenario where a block had already been delivered, and passed identically with the drain gate removed.

    That ending is a bare re-raise rather than an error frame, which is the shape `deferred.md` §5 already records as inconsistent. Pinned here as it is, not as it should be: this test is about the attempt that was not made, and dressing up the ending would make it a second test of something else.
    """
    calls: list[int] = []

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    def draining_upstream(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        # Resolved when upstream is first asked, by which point `make_client` has returned and bound it.
        chain = getattr(cast(Any, client.app).state, CHAIN_STATE_KEY)
        chain.active_requests.begin_draining()
        return httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        )

    client, _ = make_client(draining_upstream)
    with pytest.raises(httpx2.RemoteProtocolError):
        _ = _delivered(client)

    assert len(calls) == 1, "a draining process opened another upstream request"


def test_a_tear_after_a_turn_that_ran_out_of_room_is_reported_alongside_the_hand_over(
    request_log: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The two are not alternatives, and writing them as one killed the newer of them.

    `assembler.terminal.seen` does not mean the client is owed nothing: `max_tokens` is precisely a turn whose terminal event arrived and whose work is unfinished. So a tear afterwards makes *both* facts true — the turn is handed back, and the connection dropped — and the first version put them in an `if/elif` against a single `detail`. A review measured the result through the real app: `status=retry`, the hand-over's detail on the line, and the tear reported nowhere at all.

    Its own field for that reason. It is not an ending and it does not set the status; a `max_tokens` that tears is still `retry`, because the client still holds a turn to carry on.
    """
    body = sse_upstream("first").partition(b"event: message_delta")[0] + (
        b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},'
        b'"usage":{"output_tokens":7}}\n\n'
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    )

    async def finishes_short_then_breaks() -> AsyncIterator[bytes]:
        yield body
        raise httpx2.RemoteProtocolError("peer reset after the last frame")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200,
            content=finishes_short_then_breaks(),
            headers={"content-type": "text/event-stream"},
        )
    )
    with caplog.at_level(logging.INFO):
        delivered = _delivered(client)

    # The hand-over still happens and still reaches the client — none of that changes.
    assert _handed_back(delivered)["input"]["category"] == "max_tokens"
    record = _records()[-1]
    assert record["status"] == "retry", "the ending is still the hand-over"
    assert "handed back" in record["detail"]
    # And the tear is on the record too, in a field of its own rather than competing for `detail`.
    assert "RemoteProtocolError" in record["tore_after_terminal"]
    assert "peer reset after the last frame" in record["tore_after_terminal"]
    line = next(item for item in _request_lines(caplog.records) if "handed back" in item)
    assert "upstream closed abruptly after finishing the turn" in line, (
        "the hand-over detail took the whole line and the tear was reported nowhere"
    )


def test_a_turn_that_ran_out_of_room_is_handed_back_the_same_way() -> None:
    """Nothing failed — upstream finished cleanly and said it stopped for want of room — but the turn is no more finished than a torn one.

    So it takes the same ending. Ruled 2026-08-21: `max_tokens` always hands over, and never replays, since a second identical attempt would run out of room in the same place.
    """
    body = sse_upstream("first").partition(b"event: message_delta")[0] + (
        b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},'
        b'"usage":{"output_tokens":7}}\n\n'
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    )
    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    )
    delivered = _delivered(client)

    handed = _handed_back(delivered)
    assert handed["input"]["category"] == "max_tokens"
    # The other half of the same wiring. `category` already carries the stop reason, so a `message` equal to it — which is what this field used to be — spends a field repeating one. A review cut this branch back to the bare `stop_reason` and every test above stayed green, because none of them looked at it.
    message = cast(str, handed["input"]["message"])
    assert message != "max_tokens"
    assert "stop_reason=max_tokens" in message
    assert re.search(r"\[request [0-9a-f-]{36}, attempt 1\]", message) is not None
    assert b'"stop_reason":"tool_use"' in delivered
    # The reason upstream gave is not what goes on the wire — the turn now ends in a tool call — but what it produced is still delivered.
    assert b'"text":"first"' in delivered


def test_a_client_request_in_another_format_is_not_handed_a_tool_call() -> None:
    """The block is Anthropic's shape and the mechanism rests on a Claude Code behaviour. `upstream-retry-and-continuation.md` accepts that limit rather than guessing at other harnesses."""

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: response.output_item.added\n'
            b'data: {"output_index":0,"item":{"type":"message","id":"m1"}}\n\n'
            b'event: response.output_item.done\n'
            b'data: {"output_index":0,"item":{"type":"message","id":"m1","status":"completed"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    # No hand-over means the ending is what it always was: the tear reaches the caller and the connection is cut, which is what this harness surfaces as the exception.
    with pytest.raises(httpx2.RemoteProtocolError), client.stream(
        "POST", "/responses", json={"model": "gpt-model", "input": [], "stream": True}
    ) as response:
        b"".join(response.iter_bytes())


def test_a_handed_back_turn_is_neither_a_success_nor_a_failure_on_the_line() -> None:
    """Both at once, which is why it has a tier of its own.

    The client got a complete, well-formed reply and will act on it, so calling the line a failure says it got nothing. The upstream attempt behind it did not finish, so calling it a success hides every interrupted turn — and that count is the only thing that would ever show how often this is happening.
    """

    async def torn_body() -> AsyncIterator[bytes]:
        yield sse_upstream("first").partition(b"event: message_delta")[0]
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    _delivered(client)

    record = _records()[-1]
    assert record["status"] == "retry"
    # The status code is upstream's own and was settled long before this ending; it does not change.
    assert record["status_code"] == 200


def test_a_turn_upstream_finished_is_not_handed_back_when_the_connection_goes_after() -> None:
    """Nothing is missing, so nothing is handed over.

    A tool call here would tell the client to carry on from an answer that is already whole, and it would look exactly like a real one — format-valid output that is simply wrong, which is worse than the visible failure it replaced. The three endings the decision names are not interchangeable: a finished turn folded in with an abandoned one is what produced this.
    """

    async def finished_then_torn() -> AsyncIterator[bytes]:
        yield sse_upstream("complete")
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=finished_then_torn(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    delivered = _delivered(client)

    assert b"turn_interrupted" not in delivered
    assert b'"text":"complete"' in delivered
    assert b'"stop_reason":"end_turn"' in delivered
    assert b"message_stop" in delivered
    assert _records()[-1]["status"] == "ok"


def test_a_hand_back_on_the_translation_leg_counts_the_client_s_own_messages() -> None:
    """The primary path, and the one number on the block that a stand-in sample cannot check.

    `num_messages` is what the MCP server uses to notice a loop that is not advancing, and it only means that if it counts what the *client* counts: on this leg one Anthropic message becomes several Responses items, so the translated body gives a different number that advances by a different amount per turn.

    Three messages in, three asserted. A fixture with an empty conversation makes the assertion vacuous — zero is what both readings produce.
    """

    async def torn_body() -> AsyncIterator[bytes]:
        yield (
            b'event: response.output_item.added\n'
            b'data: {"output_index":0,"item":{"type":"message","id":"m1"}}\n\n'
            b'event: response.output_text.delta\n'
            b'data: {"output_index":0,"item_id":"m1","delta":"partial"}\n\n'
            b'event: response.output_item.done\n'
            b'data: {"output_index":0,"item":{"type":"message","id":"m1","status":"completed"}}\n\n'
        )
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=torn_body(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    with client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "gpt-model",
            "stream": True,
            "messages": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        },
    ) as response:
        delivered = b"".join(response.iter_bytes())

    handed = _handed_back(delivered)
    assert handed["input"]["num_messages"] == 3
    assert handed["input"]["category"] == "network"
    # What the client had already been given survives the hand-over.
    assert b'"text":"partial"' in delivered


def test_a_finished_turn_on_the_translation_leg_is_not_handed_back_either() -> None:
    """The same rule as the Anthropic-direct case, asserted on the primary path.

    The other test of this uses a leg that needs no translation, and the previous two blockers in this area were each hidden by a sample that skipped the step that broke. A rule worth having is worth asserting where the product actually runs.
    """

    async def finished_then_torn() -> AsyncIterator[bytes]:
        yield responses_sse_upstream()
        raise httpx2.RemoteProtocolError("peer closed the connection")

    client, _ = make_client(
        lambda _: httpx2.Response(
            200, content=finished_then_torn(), headers={"content-type": "text/event-stream"}
        ),
        overrides={"upstream_request_retry": {"max_total": 0}},
    )
    with client.stream(
        "POST",
        "/v1/messages",
        json={"model": "gpt-model", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as response:
        delivered = b"".join(response.iter_bytes())

    assert b"turn_interrupted" not in delivered
    assert b"message_stop" in delivered
    assert _records()[-1]["status"] == "ok"


def delivering(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    buffer: BlockBuffer,
    settings: StreamSettings,
    framer: OutboundFramer,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
) -> AsyncGenerator[bytes]:
    """`stream_delivery` with the upstream side named, which in a test is the whole of what was passed.

    Production composes four wrappers over the raw response and puts the marker in the middle of them — five objects in all — because `_counted_upstream` above it is this side's bookkeeping. A test hands over one iterator and nothing wraps it, so the marker is that iterator — which is exactly why it is spelled out here rather than defaulted inside `stream_delivery`: the default that is right for every test is the one that was wrong in production.
    """
    source = UpstreamSource(chunks)
    return stream_delivery(
        source,
        assembler,
        upstream=source,
        buffer=buffer,
        settings=settings,
        framer=framer,
        replay=replay,
        continuation=continuation,
    )
