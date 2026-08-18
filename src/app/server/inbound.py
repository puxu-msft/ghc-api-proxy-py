"""Inbound format parsing.

MAIN.md gives the endpoint list, and each one fixes the wire format its body arrives in.
The format is therefore a property of the route rather than something to sniff from the body.

Parsing here stays basic on purpose.
It names the format, the model and whether streaming was asked for; the rest is the pipeline's.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.request_headers import forwarded_client_headers


class InboundRequestError(ValueError):
    """The request cannot be turned into a context, so it never reaches the pipeline."""


@dataclass(frozen=True, slots=True)
class InboundRoute:
    path: str
    wire_format: WireFormat
    streamable: bool = True
    count_tokens: bool = False


# The OpenAI-compatible group is also mounted under /v1 and /openai/v1, per MAIN.md.
OPENAI_PREFIXES = ("", "/v1", "/openai/v1")

ROUTES: tuple[InboundRoute, ...] = (
    InboundRoute("/v1/messages", WireFormat.ANTHROPIC_MESSAGES),
    InboundRoute(
        "/v1/messages/count_tokens",
        WireFormat.ANTHROPIC_MESSAGES,
        streamable=False,
        count_tokens=True,
    ),
    InboundRoute("/chat/completions", WireFormat.OPENAI_CHAT_COMPLETIONS),
    InboundRoute("/responses", WireFormat.OPENAI_RESPONSES),
    InboundRoute("/embeddings", WireFormat.OPENAI_EMBEDDINGS, streamable=False),
)

_BY_PATH: dict[str, InboundRoute] = {}
for _route in ROUTES:
    _BY_PATH[_route.path] = _route
    if _route.wire_format is not WireFormat.ANTHROPIC_MESSAGES:
        for _prefix in OPENAI_PREFIXES:
            _BY_PATH.setdefault(f"{_prefix}{_route.path}", _route)


def route_for_path(path: str) -> InboundRoute | None:
    """Find the route a path belongs to, including the OpenAI-compatible prefixes."""
    return _BY_PATH.get(path.rstrip("/") or "/")


def build_context(
    route: InboundRoute,
    payload: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> RequestContext:
    """Turn a parsed body into a RequestContext.

    A missing or non-string model is rejected here rather than downstream.
    Routing cannot fail closed on a capability if it never learned which model to ask about.

    Headers are filtered here rather than at the send site so that nothing downstream ever holds
    the client's credentials.
    """
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InboundRequestError("request body must carry a non-empty string model")

    stream = bool(payload.get("stream", False))
    if stream and not route.streamable:
        raise InboundRequestError(f"{route.path} does not support streaming")

    context = RequestContext(
        inbound_format=route.wire_format,
        requested_model=model.strip(),
        payload=dict(payload),
        stream=stream,
        client_headers=forwarded_client_headers(headers or {}),
    )
    if route.count_tokens:
        context.extras["count_tokens"] = True
    return context
