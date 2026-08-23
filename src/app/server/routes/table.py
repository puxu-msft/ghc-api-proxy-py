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
    # Also registered under `/v1` and `/openai/v1`, per `api.md`. Explicit rather than inferred from the format: the Azure paths carry OpenAI bodies but are already fully qualified, and deriving this from the format name would have mounted them a second time underneath a prefix.
    openai_prefixed: bool = False
    # Which path parameter names the model, for endpoints whose body does not. Empty means the body carries it.
    model_from_path: str = ""
    # The path is served, but no translator answers to its format yet. A request reaching it is told so rather than being handed to the pipeline, which would report the proxy's missing capability as a fault in the client's body.
    implemented: bool = True


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
    InboundRoute("/chat/completions", WireFormat.OPENAI_CHAT_COMPLETIONS, openai_prefixed=True),
    InboundRoute("/responses", WireFormat.OPENAI_RESPONSES, openai_prefixed=True),
    InboundRoute(
        "/embeddings", WireFormat.OPENAI_EMBEDDINGS, streamable=False, openai_prefixed=True
    ),
    # Azure sends an OpenAI body to a path that names the deployment, and the deployment is the model. The old `adapt_azure_payload` performed no Azure-specific reshaping beyond copying the body and setting `model` from that segment; everything else those paths need is what the shared pipeline already does for the unqualified ones.
    InboundRoute(
        "/openai/deployments/{deployment}/chat/completions",
        WireFormat.OPENAI_CHAT_COMPLETIONS,
        model_from_path="deployment",
    ),
    InboundRoute(
        "/openai/deployments/{deployment}/responses",
        WireFormat.OPENAI_RESPONSES,
        model_from_path="deployment",
    ),
    InboundRoute(
        "/openai/deployments/{deployment}/embeddings",
        WireFormat.OPENAI_EMBEDDINGS,
        streamable=False,
        model_from_path="deployment",
    ),
    # Gemini puts the model and the method in one segment, `{model}:{method}`. Registered as three templates rather than one `{model_and_method}` catch-all, which is what this was first written as: the catch-all matched any single segment, so `/v1beta/models/gemini-pro` and `/v1beta/models/anything` answered as ratified endpoints too, and the method set `api.md` names stopped being a boundary anything enforced. Measured — the greedy segment still captures a model that contains colons, so `vendor:family:generateContent` resolves to `vendor:family`.
    # Routed now and answered with a refusal, because a path `api.md` ratifies should say "not yet" rather than being indistinguishable from an endpoint this proxy does not have.
    # No `streamable` on any of the three, deliberately. `build_context` reads streaming off the body's `stream` field and Gemini's body has none — which of these paths streams is the method segment's job — so a value here would encode a mechanism that does not apply to them, and would read as a decision already wired. `model_from_path` and `count_tokens` are both correct and are what the implementation will use; nothing consults them while `implemented` is false.
    InboundRoute(
        "/v1beta/models/{model}:generateContent",
        WireFormat.GEMINI_GENERATE_CONTENT,
        model_from_path="model",
        implemented=False,
    ),
    InboundRoute(
        "/v1beta/models/{model}:streamGenerateContent",
        WireFormat.GEMINI_GENERATE_CONTENT,
        model_from_path="model",
        implemented=False,
    ),
    InboundRoute(
        "/v1beta/models/{model}:countTokens",
        WireFormat.GEMINI_GENERATE_CONTENT,
        count_tokens=True,
        model_from_path="model",
        implemented=False,
    ),
)


def expanded_paths(route: InboundRoute) -> tuple[str, ...]:
    """Every path this route answers on.

    One function because there are two consumers — the router that registers them and the lookup that maps them back — and a rule written twice is a rule that can be changed once. A route registered but absent from the lookup answers 404 from `_dispatch`'s defensive branch, which is the same 404 a genuinely unmounted path gives, so the failure would be invisible from the outside.
    """
    if route.openai_prefixed:
        return tuple(f"{prefix}{route.path}" for prefix in OPENAI_PREFIXES)
    return (route.path,)


_BY_PATH: dict[str, InboundRoute] = {}
for _route in ROUTES:
    for _path in expanded_paths(_route):
        _BY_PATH.setdefault(_path, _route)


def route_for_path(path: str) -> InboundRoute | None:
    """Find the route a path belongs to, including the OpenAI-compatible prefixes.

    A route carrying parameters is found by its **template**, not by a URL that matched it — the two differ once a segment is a parameter, and only the template is a key here. `_dispatch` reads it off the ASGI scope, where the router records which of its own paths answered. For the routes whose paths are literal the two spellings coincide, which is why callers that pass a URL still resolve.
    """
    return _BY_PATH.get(path.rstrip("/") or "/")
