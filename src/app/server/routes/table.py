"""Which path is which endpoint, and what wire format its body arrives in.

Split out of `app.server.inbound` on 2026-08-22, when `server/routes/` was created for the name `docs/.human-controlled/module-org.md` has ratified all along. The table is route knowledge; turning a body into a `RequestContext` is codec work, and that stayed behind in `inbound`.
"""

from dataclasses import dataclass

from app.pipeline.request import WireFormat


@dataclass(frozen=True, slots=True)
class InboundRoute:
    path: str
    wire_format: WireFormat
    streamable: bool = True
    count_tokens: bool = False


# The OpenAI-compatible group is also mounted under /v1 and /openai/v1, per `docs/.human-controlled/api.md`.
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
