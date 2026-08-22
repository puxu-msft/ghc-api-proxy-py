from collections.abc import Coroutine, Mapping
from typing import Any, cast

import httpx2
from anthropic import AsyncAnthropic
from anthropic._types import Body as AnthropicBody
from h2.exceptions import ProtocolError as H2ProtocolError
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import APIStatusError as OpenAIAPIStatusError
from openai import AsyncOpenAI
from openai._types import Body as OpenAIBody

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.errors import normalize_upstream_error
from app.model_provider.ghc_client.headers import build_request_headers
from app.model_provider.ghc_client.tokens import CopilotTokenManager
from app.model_provider.ghc_client.transport import (
    ResponsesHeadersPendingTransportError,
    is_responses_headers_pending_transport_error,
)


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

    async def request_headers(
        self,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """The upstream headers, with anything the caller adds underneath rather than on top.

        `build_request_headers` already says the protocol and identity fields are owned by this library, and they have to be: the identity set makes the request look like Copilot Chat, and upstream rejects requests that do not. A caller forwarding a client's headers would otherwise replace `user-agent` — or `Authorization` — without anything failing loudly.

        **Compared case-insensitively, which it was not until 2026-08-22.** `{**extra, **owned}` only lets the owned value win when the two spellings are byte-equal, and they are not: this library writes `Authorization`, `X-Interaction-Id`, `X-Interaction-Type` and `X-Agent-Task-Id` capitalised while a forwarded client header arrives lowercased. Two dict keys, both surviving. Measured 2026-08-22 under `httpx2.MockTransport`: on the Anthropic SDK path the collision is folded away by `httpx2.Headers.__setitem__` and the owned value does win, but on the OpenAI SDK path `_build_request` reads `headers.multi_items()` and **both `authorization` lines go out on the wire**. The safe behaviour there rested on one SDK's internals rather than on anything this function did, so it is now this function that does it.
        """
        token = await self._tokens.get_token()
        headers = build_request_headers(
            token,
            self._config,
            interaction_id=self._interaction_id,
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

    async def _post_openai(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        stream: bool,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._openai.post(
            path,
            cast_to=httpx2.Response,
            body=cast(OpenAIBody, dict(payload)),
            options={"headers": await self.request_headers(extra_headers=extra_headers)},
            stream=stream,
        )

    async def _post_anthropic(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        stream: bool,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._anthropic.post(
            path,
            cast_to=httpx2.Response,
            body=cast(AnthropicBody, dict(payload)),
            options={"headers": await self.request_headers(extra_headers=extra_headers)},
            stream=stream,
        )

    @staticmethod
    async def _in_pipeline_terms(post: Coroutine[Any, Any, httpx2.Response]) -> httpx2.Response:
        """Await one SDK call, raising the pipeline's error for an upstream failure.

        Applied per send method rather than inside `_post_*` because `send_responses_headers` deliberately catches the SDK's own status error to read the response off it, and that contract belongs to the existing chain.
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
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_openai(
                "/chat/completions",
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        )

    async def send_anthropic_messages(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_anthropic(
                "/v1/messages",
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_anthropic("/v1/messages/count_tokens", payload, stream=False)
        )

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_openai(
                "/responses",
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        )

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        """A Responses request whose error status is returned rather than raised.

        The asymmetry with the other methods is deliberate: the caller reads the error headers.
        A transport failure before headers arrive is normalised into a retryable category.
        """
        try:
            return await self._post_openai("/responses", payload, stream=True)
        except OpenAIAPIStatusError as error:
            return error.response
        except (httpx2.TransportError, OpenAIAPIConnectionError, H2ProtocolError) as error:
            # `H2ProtocolError` is named here because it is not an httpx error and nothing wraps it: httpcore guards only the socket read, so a GOAWAY arriving in the same read as the frames after it raises straight through. Without this it would leave as an unhandled exception and never reach the classifier at all.
            if is_responses_headers_pending_transport_error(error):
                raise ResponsesHeadersPendingTransportError(error) from error
            raise

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._in_pipeline_terms(
            self._post_openai("/embeddings", payload, stream=False)
        )
