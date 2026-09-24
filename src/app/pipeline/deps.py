"""What the driver reads off the object graph, and nothing else.

`app.pipeline.driver` owns the request lifecycle but must not depend on
`app.core.chain` — the assembly record — to say what it needs. Depending on the
record means depending on everything the record holds, which is how importing the
driver came to import the observability store, the tokenization worker and the
history writer's types whether the driver touched them or not.

This protocol is the complete list of what the driver reads, nothing more. `Chain`
satisfies it structurally; that check happens where the two meet, in `app.server`,
which is the only place allowed to know both.
"""

import re
from typing import Protocol

from app.config.schema import ProxyConfig
from app.model_provider import ProviderRegistry
from app.observability.active_requests import ActiveRequestRegistry
from app.pipeline.events import FrozenSubscribers
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.pipeline.translation_driver.reasoning import CompiledThinkingProfiles
from app.pipeline.translation_driver.registry import TranslatorRegistry
from app.tokenization.admission import PromptTokenAdmission
from app.tokenization.learning import TokenLearningService
from app.tokenization.state_store import TokenizationStateStore
from app.tokenization.worker import LocalTokenWorker


class DriverDeps(Protocol):
    """The eleven things the driver reads. Counted, so growth shows."""

    config: ProxyConfig
    providers: ProviderRegistry
    translators: TranslatorRegistry
    subscribers: FrozenSubscribers[RequestContext]
    active_requests: ActiveRequestRegistry
    tokenization: TokenizationStateStore
    local_token_worker: LocalTokenWorker
    prompt_token_admission: PromptTokenAdmission
    token_learning: TokenLearningService
    beta_flag_denials: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...]
    thinking_profiles: CompiledThinkingProfiles

    def rate_limiter_for(self, provider_name: str) -> RateLimiter: ...
