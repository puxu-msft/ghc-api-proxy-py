from collections.abc import Coroutine, Mapping
from typing import Any, cast

import httpx2
from anthropic import AsyncAnthropic
from anthropic._types import Body as AnthropicBody
from openai import AsyncOpenAI
from openai._types import Body as OpenAIBody

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_request_headers
from app.model_provider.ghc_client.tokens import CopilotTokenManager
from app.model_provider.upstream_errors import normalize_upstream_error
from app.observability.raw_capture import (
    activate_pending_upstream_capture,
    observe_active_upstream_request_hook,
)
from app.pipeline.exceptions import (
    ConnectionBoundInputIdRetry,
    UpstreamError,
    is_connection_bound_input_id_error,
)


def _install_raw_capture_request_hook(sdk_client: object) -> None:
    http_client = getattr(sdk_client, "_client", None)
    if not isinstance(http_client, httpx2.AsyncClient):
        return
    request_hooks = http_client.event_hooks["request"]
    if observe_active_upstream_request_hook not in request_hooks:
        request_hooks.append(observe_active_upstream_request_hook)


class GhcApiClient:
    """Sends model-agnostic requests to the GitHub Copilot upstream.

    Builds auth headers and posts payloads.
    It does not resolve model names, translate bodies between protocols, or orchestrate retries.
    Every method returns the raw `httpx.Response` for the caller to consume.
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        anthropic_client: AsyncAnthropic,
        tokens: CopilotTokenManager,
        config: GhcClientConfig,
        *,
        interaction_id: str,
    ) -> None:
        self._openai = openai_client
        self._anthropic = anthropic_client
        self._tokens = tokens
        self._config = config
        self._interaction_id = interaction_id
        _install_raw_capture_request_hook(openai_client)
        _install_raw_capture_request_hook(anthropic_client)

    async def headers_for_interaction(
        self,
        interaction_id: str,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Build headers for one explicit Copilot interaction.

        `build_request_headers` already says the protocol and identity fields are owned by this library, and they have to be: the identity set makes the request look like Copilot Chat, and upstream rejects requests that do not. A caller forwarding a client's headers would otherwise replace `user-agent` — or `Authorization` — without anything failing loudly.

        **Compared case-insensitively, which it was not until 2026-08-22.** `{**extra, **owned}` only lets the owned value win when the two spellings are byte-equal, and they are not: this library writes `Authorization`, `X-Interaction-Id`, `X-Interaction-Type` and `X-Agent-Task-Id` capitalised while a forwarded client header arrives lowercased. Two dict keys, both surviving. Measured 2026-08-22 under `httpx2.MockTransport`: on the Anthropic SDK path the collision is folded away by `httpx2.Headers.__setitem__` and the owned value does win, but on the OpenAI SDK path `_build_request` reads `headers.multi_items()` and **both `authorization` lines go out on the wire**. The safe behaviour there rested on one SDK's internals rather than on anything this function did, so it is now this function that does it.
        """
        token = await self._tokens.get_token()
        headers = build_request_headers(
            token,
            self._config,
            interaction_id=interaction_id,
        )
        if extra_headers:
            owned = {name.lower() for name in headers}
            headers = {
                **{
                    str(key): str(value)
                    for key, value in extra_headers.items()
                    if str(key).lower() not in owned
                },
                **headers,
            }
        return headers

    async def catalog_headers(
        self,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Build headers for provider-owned catalog traffic without a client session."""
        return await self.headers_for_interaction(
            self._interaction_id,
            extra_headers=extra_headers,
        )

    async def _post_openai(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        stream: bool,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str,
    ) -> httpx2.Response:
        headers = await self.headers_for_interaction(
            interaction_id,
            extra_headers=extra_headers,
        )
        with activate_pending_upstream_capture():
            return await self._openai.post(
                path,
                cast_to=httpx2.Response,
                body=cast(OpenAIBody, dict(payload)),
                options={"headers": headers},
                stream=stream,
            )

    async def _post_anthropic(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        stream: bool,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str,
    ) -> httpx2.Response:
        headers = await self.headers_for_interaction(
            interaction_id,
            extra_headers=extra_headers,
        )
        with activate_pending_upstream_capture():
            return await self._anthropic.post(
                path,
                cast_to=httpx2.Response,
                body=cast(AnthropicBody, dict(payload)),
                options={"headers": headers},
                stream=stream,
            )

    @staticmethod
    async def _in_pipeline_terms(post: Coroutine[Any, Any, httpx2.Response]) -> httpx2.Response:
        """Await one SDK call, raising the pipeline's error for an upstream failure.

        Applied per send method rather than inside `_post_*`. The reason used to be `send_responses_headers`, which deliberately caught the SDK's own status error to read the response off it; that method was archived on 2026-08-23 with the chain nothing instantiates. The shape is kept because it is the seam where a send method may still opt out — nothing does today.
        """
        try:
            return await post
        except BaseException as error:
            normalized = normalize_upstream_error(error)
            if normalized is None:
                raise
            raise normalized from error

    async def send_chat_completions(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str,
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_openai(
                "/chat/completions",
                payload,
                stream=stream,
                extra_headers=extra_headers,
                interaction_id=interaction_id,
            )
        )

    async def send_anthropic_messages(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str,
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_anthropic(
                "/v1/messages",
                payload,
                stream=stream,
                extra_headers=extra_headers,
                interaction_id=interaction_id,
            )
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_anthropic(
                "/v1/messages/count_tokens",
                payload,
                stream=False,
                interaction_id=self._interaction_id,
            )
        )

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str,
    ) -> httpx2.Response:
        try:
            return await self._in_pipeline_terms(
                self._post_openai(
                    "/responses",
                    payload,
                    stream=stream,
                    extra_headers=extra_headers,
                    interaction_id=interaction_id,
                )
            )
        except UpstreamError as error:
            if not is_connection_bound_input_id_error(error):
                raise
            raise ConnectionBoundInputIdRetry(error, dict(payload)) from error

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
        *,
        interaction_id: str,
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_openai(
                "/embeddings",
                payload,
                stream=False,
                interaction_id=interaction_id,
            )
        )
