"""The object graph one request is served from.

Here rather than beside the code that builds it, and that separation is the point: `app.server`, `app.pipeline` and `app.debug` all need the *type*, while only the entry point needs the builders. While the two lived in one module, needing the type meant importing the builders' whole world — `app.server` itself, the entire `app.upstream` package, the GHC auth stack, all six direct drivers and all five built-in subscribers. Measured 2026-08-22 by importing each into a fresh interpreter and counting `app.*` in `sys.modules`: **importing this module brings 83, `app.server.composition` brings 106, and `app.server` is no longer among the 83**. The sharpest form of that is the control rather than the difference — `import app.server` now pulls in exactly one module, itself.

(Two numbers from the same day, 81 and 104, appear in the session's own record and in `.dev/docs/server-layout/`. They are the same measurement taken before the move, when neither `app.core` nor `app.core.chain` existed to be counted. 83 and 106 are what a reader can reproduce today, with `.dev/docs/server-layout/probes/reach.py`.)

It is not a leaf, and saying so is more useful than pretending: `TranslatorRegistry`, `FrozenSubscribers[RequestContext]` and `RateLimiter` are pipeline types, so 25 `app.pipeline` modules come with the record no matter where it lives. Making *that* number smaller is a different question — whether a driver should take a `Chain` at all, or read typed facts — and it is registered in `.dev/docs/server-layout/`, not answered here.

`core` is where it goes because this package already states the rule: facts shared across domains, owned by none of them. A record that `server`, `pipeline` and `debug` all read cannot live inside any one of them without making that one a dependency of the others.
"""

import re
from dataclasses import dataclass, field

import httpx2

from app.config.paths import tokenization_state_path
from app.config.schema import ProxyConfig
from app.model_provider import ProviderRegistry
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.terminal import TerminalCapabilities, detect_terminal
from app.pipeline.events import FrozenSubscribers
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.pipeline.translation_driver.registry import TranslatorRegistry
from app.tokenization.admission import PromptTokenAdmission
from app.tokenization.state_store import TokenizationStateStore


@dataclass(slots=True)
class Chain:
    """Everything a request handler needs, built once."""

    config: ProxyConfig
    providers: ProviderRegistry
    translators: TranslatorRegistry
    subscribers: FrozenSubscribers[RequestContext]
    http_client: httpx2.AsyncClient
    rate_limiters: dict[str, RateLimiter] = field(default_factory=lambda: dict[str, RateLimiter]())
    # One outbound client per provider, held here so shutdown can reach them. Not an optimisation in reverse — sharing one client shares its **connection pool**, and two providers pointed at the same host (which is the default: both are `api.githubcopilot.com`) then ride the same TCP connections. A GOAWAY raised by one account's traffic ends the other's in-flight streams, and `max_streams_per_connection` does not help, because it bounds how many requests share a connection rather than whose they are. Spec §8.1.
    provider_clients: dict[str, httpx2.AsyncClient] = field(
        default_factory=lambda: dict[str, httpx2.AsyncClient]()
    )
    # Who is in flight right now. Always maintained, whether or not anything renders it: the cost is one dict entry per request, and making it conditional would mean the footer shows an empty line for its first few seconds after being switched on.
    active_requests: ActiveRequestRegistry = field(default_factory=ActiveRequestRegistry)
    # Probed once, here, and shared by the footer and the log lines. Asking twice invites two answers that disagree, and a log stream that emits a glyph the footer has already decided this terminal cannot encode is exactly the kind of split nobody thinks to look for.
    capabilities: TerminalCapabilities = field(default_factory=detect_terminal)
    # What the `local` token counter has learnt. Constructing it touches nothing; `load()` does.
    tokenization: TokenizationStateStore = field(
        default_factory=lambda: TokenizationStateStore(tokenization_state_path())
    )
    # One process-wide worker permit for the exceptional large-field path. Ordinary requests stay on the byte fast path and never acquire it.
    prompt_token_admission: PromptTokenAdmission = field(default_factory=PromptTokenAdmission)
    # `strip_anthropic_beta_flags` compiled, in the order the operator wrote it. Same reason as `web_search_models` above it: a pattern that does not compile belongs to the config, so it should stop start-up rather than the first request that happens to reach the table.
    beta_flag_denials: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = ()

    def rate_limiter_for(self, provider_name: str) -> RateLimiter:
        return self.rate_limiters[provider_name]

    async def aclose(self) -> None:
        """Release what this chain created, which is the per-provider clients and nothing else.

        `http_client` is **not** closed here. It is built by the caller — to resolve base URLs before this chain exists — and closing it from both sides is how one of them ends up closing a client the other still holds. Whoever built it closes it; `cli.py` does, in the same `finally` that calls this.
        """
        for client in self.provider_clients.values():
            await client.aclose()
