"""The object graph one request is served from.

Here rather than beside the code that builds it, and that separation is the point: `app.server`, `app.pipeline` and `app.debug` all need the *type*, while only the entry point needs the builders. While the two lived in one module, needing the type meant importing the builders' whole world — measured 2026-08-22, 104 `app.*` modules including `app.server` itself, the entire `app.upstream` package, the GHC auth stack, all six direct drivers and all five built-in subscribers. Importing this module brings 81, and `app.server` is no longer one of them.

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
    # Who is in flight right now. Always maintained, whether or not anything renders it: the cost is one dict entry per request, and making it conditional would mean the footer shows an empty line for its first few seconds after being switched on.
    active_requests: ActiveRequestRegistry = field(default_factory=ActiveRequestRegistry)
    # Probed once, here, and shared by the footer and the log lines. Asking twice invites two answers that disagree, and a log stream that emits a glyph the footer has already decided this terminal cannot encode is exactly the kind of split nobody thinks to look for.
    capabilities: TerminalCapabilities = field(default_factory=detect_terminal)
    # What the `local` token counter has learnt. Constructing it touches nothing; `load()` does.
    tokenization: TokenizationStateStore = field(
        default_factory=lambda: TokenizationStateStore(tokenization_state_path())
    )
    # `strip_anthropic_beta_flags` compiled, in the order the operator wrote it. Same reason as `web_search_models` above it: a pattern that does not compile belongs to the config, so it should stop start-up rather than the first request that happens to reach the table.
    beta_flag_denials: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = ()

    def rate_limiter_for(self, provider_name: str) -> RateLimiter:
        return self.rate_limiters[provider_name]

    async def aclose(self) -> None:
        await self.http_client.aclose()
