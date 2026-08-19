"""End-to-end over the new chain: HTTP in, upstream out, through a real ASGI app.

The upstream is a MockTransport under the real SDKs.
Upstream protocol behaviour is therefore the real thing rather than a friendlier stand-in.
"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import orjson
import pytest
from anthropic import AsyncAnthropic
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config.schema import ModelProviderConfig, ProxyConfig
from app.ghc_client import GhcApiClient, GhcClientConfig
from app.ghc_client.tokens import CopilotTokenManager
from app.model_provider import GithubCopilotProvider, ModelProvider
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app
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


def test_count_tokens_refuses_a_model_that_advertises_other_endpoints() -> None:
    """The gap between refusal and failure.

    `gpt-model` is routable and known — it just cannot take a Messages body. Treating that refusal
    as one more failed attempt would fall through to the local estimate and answer 200 with a count
    for a model this request can never reach. `mute-model` does not exercise this: it is stopped
    earlier, by routing.
    """
    client, seen = make_client(lambda _: httpx.Response(200, json={"input_tokens": 99}))
    response = client.post(
        "/v1/messages/count_tokens",
        json={"model": "gpt-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "EndpointNotSupported"
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
