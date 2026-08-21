from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import uuid4

import anyio
import httpx2

from app.anthropic.client import AnthropicClient
from app.anthropic.thinking.quarantine import ThinkingQuarantineStore
from app.auth.providers import (
    CLITokenProvider,
    EnvTokenProvider,
    FileTokenProvider,
    GitHubTokenManager,
)
from app.config.paths import user_data_path
from app.ghc_client import (
    CopilotTokenManager,
    GitHubAccountClient,
    infer_account_type,
)
from app.openai.client import OpenAIClient
from app.openai.responses_ws import ResponsesWebSocketClient
from app.runtime import RuntimeState
from app.tokenization.estimators import preload_tokenizer
from app.tokenization.service import AnthropicTokenCountingService
from app.tokenization.state_store import TokenizationStateStore
from app.transform.model_resolver import ModelResolver
from app.upstream.base import UpstreamTarget
from app.upstream.client import (
    SDKClients,
    create_copilot_sdk_clients,
    create_http_client,
    create_sdk_clients,
)
from app.upstream.copilot import (
    CopilotUpstream,
    GitHubTokenSourceAdapter,
    build_copilot_headers,
    build_copilot_identity_headers,
)
from app.upstream.generic import GenericUpstream
from app.upstream.models_api import ModelCatalog
from app.upstream.urls import resolve_copilot_base_url

type AccountType = Literal["individual", "business", "enterprise", "self-hosted"]


class RefreshableModelCatalog(Protocol):
    async def refresh(self, headers: Mapping[str, str]) -> bool: ...


@dataclass(slots=True)
class UpstreamServices:
    http_client: httpx2.AsyncClient
    sdk_clients: SDKClients
    target: UpstreamTarget
    model_catalog: ModelCatalog
    model_resolver: ModelResolver
    github_tokens: GitHubTokenManager | None = None
    copilot_tokens: CopilotTokenManager | None = None
    resolved_account_type: AccountType | None = None
    model_headers: Callable[[], Awaitable[dict[str, str]]] | None = None

    async def run_model_refresh_loop(self, interval_seconds: float) -> None:
        if self.model_headers is None:
            raise RuntimeError("model header provider is not configured")
        await run_model_refresh_loop(
            self.model_catalog,
            self.model_headers,
            interval_seconds=interval_seconds,
        )


async def run_model_refresh_loop(
    catalog: RefreshableModelCatalog,
    header_provider: Callable[[], Awaitable[dict[str, str]]],
    *,
    interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
) -> None:
    while True:
        await sleep(interval_seconds)
        try:
            await catalog.refresh(await header_provider())
        except Exception:
            continue


async def initialize_upstream_services(
    runtime: RuntimeState,
    *,
    http_client: httpx2.AsyncClient | None = None,
) -> UpstreamServices:
    settings = runtime.settings
    if runtime.tokenization_state is None:
        runtime.tokenization_state = TokenizationStateStore(
            user_data_path() / "tokenization.json"
        )
        await runtime.tokenization_state.load()
    await preload_tokenizer()
    if settings.upstream.type == "generic":
        if not settings.upstream.openai_base_url:
            raise ValueError("generic upstream requires upstream.openai_base_url")
        if not settings.upstream.api_key:
            raise ValueError("generic upstream requires upstream.api_key")

    client = http_client or create_http_client(settings)
    if settings.upstream.type == "generic":
        sdk_clients = create_sdk_clients(settings, http_client=client)
        target = GenericUpstream(sdk_clients)
        catalog = ModelCatalog(
            client,
            settings.upstream.openai_base_url or "https://api.openai.com/v1",
            disabled_ids=set(settings.disabled_models),
        )
        await catalog.refresh({"Authorization": f"Bearer {settings.upstream.api_key}"})
        resolver = ModelResolver(
            available_ids=catalog.available_ids,
            model_overrides=settings.model_overrides,
            model_mappings=settings.model_mappings,
        )
        async def generic_model_headers() -> dict[str, str]:
            if not settings.upstream.api_key:
                return {}
            return {"Authorization": f"Bearer {settings.upstream.api_key}"}

        services = UpstreamServices(
            client,
            sdk_clients,
            target,
            catalog,
            resolver,
            model_headers=generic_model_headers,
        )
        runtime.models_ready = True
        runtime.github_token_ready = True
        runtime.copilot_token_ready = True
        runtime.upstream_services = services
        quarantine = ThinkingQuarantineStore(
            ttl_seconds=settings.anthropic.poisoned_thinking_ttl_hours * 3600
        )
        runtime.anthropic_client = AnthropicClient(
            target,
            resolver,
            settings,
            quarantine,
            model_catalog=catalog,
        )
        runtime.token_counter = AnthropicTokenCountingService(
            target,
            runtime.tokenization_state,
            use_upstream=settings.anthropic.use_upstream_count_tokens,
        )
        runtime.openai_client = OpenAIClient(target, resolver)
        runtime.responses_ws_client = None
        return services

    token_path = Path(settings.auth.token_file) if settings.auth.token_file else None
    file_provider = FileTokenProvider(token_path)
    github_tokens = GitHubTokenManager(
        [
            CLITokenProvider(settings.auth.github_token),
            EnvTokenProvider(),
            file_provider,
        ]
    )
    github_info = await github_tokens.get_token()
    runtime.github_token_ready = True
    copilot_tokens = CopilotTokenManager(
        GitHubTokenSourceAdapter(github_tokens),
        client,
        identity_headers=build_copilot_identity_headers(settings),
    )
    await copilot_tokens.ensure_valid_token()
    runtime.copilot_token_ready = True

    account_type = settings.auth.account_type
    if account_type is None and not settings.upstream.ghc_api_base_url:
        usage = await GitHubAccountClient(client).get_copilot_usage(github_info.token)
        inferred = infer_account_type(usage)
        account_type = cast(AccountType, inferred or "individual")
        settings = settings.model_copy(
            update={"auth": settings.auth.model_copy(update={"account_type": account_type})}
        )
    else:
        account_type = account_type or "individual"

    sdk_clients = create_copilot_sdk_clients(settings, http_client=client)
    interaction_id = str(uuid4())
    target = CopilotUpstream(
        sdk_clients,
        copilot_tokens,
        settings,
        interaction_id=interaction_id,
    )
    base_url = resolve_copilot_base_url(settings)
    catalog = ModelCatalog(client, base_url, disabled_ids=set(settings.disabled_models))
    token = await copilot_tokens.get_token()
    await catalog.refresh(
        build_copilot_headers(token, settings, interaction_id=interaction_id)
    )
    resolver = ModelResolver(
        available_ids=catalog.available_ids,
        model_overrides=settings.model_overrides,
        model_mappings=settings.model_mappings,
    )

    async def copilot_model_headers() -> dict[str, str]:
        current_token = await copilot_tokens.get_token()
        return build_copilot_headers(
            current_token,
            settings,
            interaction_id=interaction_id,
        )

    services = UpstreamServices(
        client,
        sdk_clients,
        target,
        catalog,
        resolver,
        github_tokens=github_tokens,
        copilot_tokens=copilot_tokens,
        resolved_account_type=account_type,
        model_headers=copilot_model_headers,
    )
    runtime.settings = settings
    runtime.models_ready = True
    runtime.upstream_services = services
    quarantine = ThinkingQuarantineStore(
        ttl_seconds=settings.anthropic.poisoned_thinking_ttl_hours * 3600
    )
    runtime.anthropic_client = AnthropicClient(
        target,
        resolver,
        settings,
        quarantine,
        model_catalog=catalog,
    )
    runtime.token_counter = AnthropicTokenCountingService(
        target,
        runtime.tokenization_state,
        use_upstream=settings.anthropic.use_upstream_count_tokens,
    )
    runtime.openai_client = OpenAIClient(target, resolver)
    ws_base_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
    runtime.responses_ws_client = ResponsesWebSocketClient(
        client,
        f"{ws_base_url}/responses",
        queue_size=settings.openai_responses.ws_queue_size,
    )
    return services


async def close_upstream_services(
    runtime: RuntimeState,
    *,
    close_http_client: bool = True,
) -> None:
    services = runtime.upstream_services
    if services is None:
        return
    if close_http_client:
        await services.http_client.aclose()
    runtime.upstream_services = None
    runtime.github_token_ready = False
    runtime.copilot_token_ready = False
    runtime.models_ready = False
    runtime.anthropic_client = None
    runtime.token_counter = None
    runtime.openai_client = None
    runtime.responses_ws_client = None
