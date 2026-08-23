from typing import Any

import pytest

from app.pipeline.request import WireFormat
from app.server.inbound import InboundRequestError, build_context
from app.server.routes.table import InboundRoute, route_for_path


def route(path: str) -> InboundRoute:
    found = route_for_path(path)
    assert found is not None, f"no route for {path}"
    return found


def test_each_endpoint_fixes_its_wire_format() -> None:
    # The format is a property of the route, not something sniffed from the body.
    assert route("/v1/messages").wire_format is WireFormat.ANTHROPIC_MESSAGES
    assert route("/chat/completions").wire_format is WireFormat.OPENAI_CHAT_COMPLETIONS
    assert route("/responses").wire_format is WireFormat.OPENAI_RESPONSES
    assert route("/embeddings").wire_format is WireFormat.OPENAI_EMBEDDINGS


@pytest.mark.parametrize("prefix", ["", "/v1", "/openai/v1"])
def test_openai_group_is_reachable_under_every_compatible_prefix(prefix: str) -> None:
    route = route_for_path(f"{prefix}/chat/completions")
    assert route is not None
    assert route.wire_format is WireFormat.OPENAI_CHAT_COMPLETIONS


def test_anthropic_path_is_not_remounted_under_the_openai_prefixes() -> None:
    # /v1/messages is Anthropic's own path; the compatible prefixes belong to the OpenAI group.
    assert route_for_path("/openai/v1/v1/messages") is None


def test_unknown_path_has_no_route() -> None:
    assert route_for_path("/nope") is None


def test_trailing_slash_is_tolerated() -> None:
    assert route_for_path("/responses/") is not None


def test_context_carries_the_route_format_and_the_model() -> None:
    route = route_for_path("/v1/messages")
    assert route is not None
    context = build_context(route, dict[str, Any]({"model": "  claude-model  ", "messages": []}))
    assert context.inbound_format is WireFormat.ANTHROPIC_MESSAGES
    assert context.requested_model == "claude-model"
    assert context.stream is False


def test_stream_flag_is_read_from_the_body() -> None:
    route = route_for_path("/responses")
    assert route is not None
    assert build_context(route, dict[str, Any]({"model": "m", "stream": True})).stream is True


def test_streaming_is_refused_on_a_non_streaming_endpoint() -> None:
    route = route_for_path("/embeddings")
    assert route is not None
    with pytest.raises(InboundRequestError, match="does not support streaming"):
        build_context(route, dict[str, Any]({"model": "m", "stream": True}))


def test_count_tokens_route_is_marked_and_not_streamable() -> None:
    route = route_for_path("/v1/messages/count_tokens")
    assert route is not None
    assert route.count_tokens is True
    context = build_context(route, dict[str, Any]({"model": "m"}))
    assert context.extras["count_tokens"] is True


@pytest.mark.parametrize("body", [{}, {"model": ""}, {"model": "   "}, {"model": 7}])
def test_missing_or_unusable_model_is_rejected(body: dict[str, object]) -> None:
    # Routing fails closed on capability, which it cannot do without knowing the model.
    route = route_for_path("/v1/messages")
    assert route is not None
    with pytest.raises(InboundRequestError, match="model"):
        build_context(route, body)


def test_body_is_copied_into_the_context() -> None:
    route = route_for_path("/v1/messages")
    assert route is not None
    body: dict[str, Any] = {"model": "m", "messages": []}
    context = build_context(route, body)
    context.payload["added"] = True
    assert "added" not in body


def test_a_path_named_model_reaches_the_pipeline_without_reaching_the_record() -> None:
    """Both halves of the substitution, because each fails in a different direction.

    Downstream reads `payload`, so the deployment has to be in there or nothing knows which model to route to. `original_payload` is the record of what the client sent, which `message-format-reshape.md` requires to be unaffected by anything this proxy does to the request — and putting the model there would make the record claim the client sent a field it never sent.
    """
    route = route_for_path("/openai/deployments/{deployment}/responses")
    assert route is not None
    body: dict[str, Any] = {"input": []}
    context = build_context(route, body, None, {"deployment": "gpt-model"})

    assert context.requested_model == "gpt-model"
    assert context.payload["model"] == "gpt-model"
    assert "model" not in context.original_payload
    assert "model" not in body


def test_the_deployment_in_the_path_wins_over_a_model_in_the_body() -> None:
    """A body that disagrees with the URL it was sent to does not get to redirect the request."""
    route = route_for_path("/openai/deployments/{deployment}/chat/completions")
    assert route is not None
    context = build_context(route, {"model": "somewhere-else", "messages": []}, None, {"deployment": "cc-model"})
    assert context.requested_model == "cc-model"
    assert context.payload["model"] == "cc-model"


@pytest.mark.parametrize("params", [None, {}, {"deployment": "  "}, {"deployment": 7}])
def test_a_route_that_takes_its_model_from_the_path_is_refused_without_one(
    params: dict[str, Any] | None,
) -> None:
    """Refused rather than falling back to the body: the fallback is what would make an unrouted path answer as if it had been routed."""
    route = route_for_path("/openai/deployments/{deployment}/responses")
    assert route is not None
    with pytest.raises(InboundRequestError, match="from the path"):
        build_context(route, {"model": "gpt-model", "input": []}, None, params)
