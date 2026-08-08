from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import httpx
from anthropic._types import Body as AnthropicBody
from openai import (
    APIConnectionError as OpenAIAPIConnectionError,
)
from openai import (
    APIStatusError as OpenAIAPIStatusError,
)
from openai._types import Body as OpenAIBody

from app.auth.copilot import CopilotTokenManager
from app.config.settings import AppSettings
from app.upstream.base import (
    ResponsesHeadersPendingTransportError,
    is_responses_headers_pending_transport_error,
)
from app.upstream.client import SDKClients


def build_copilot_headers(
    token: str,
    settings: AppSettings,
    *,
    interaction_id: str,
    request_id: str | None = None,
    intent: str = "conversation-panel",
    vision: bool = False,
    model_request_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    resolved_request_id = request_id or str(uuid4())
    versions = settings.headers
    headers = {
        "Authorization": f"Bearer {token}",
        "content-type": "application/json",
        "copilot-integration-id": "vscode-chat",
        "editor-version": f"vscode/{versions.vscode_version}",
        "editor-plugin-version": f"copilot-chat/{versions.copilot_version}",
        "user-agent": f"GitHubCopilotChat/{versions.copilot_version}",
        "openai-intent": intent,
        "x-github-api-version": versions.api_version,
        "x-request-id": resolved_request_id,
        "X-Interaction-Id": interaction_id,
        "X-Interaction-Type": intent,
        "X-Agent-Task-Id": resolved_request_id,
        "x-vscode-user-agent-library-version": "electron-fetch",
    }
    if vision:
        headers["copilot-vision-request"] = "true"
    if model_request_headers:
        protected = {name.lower() for name in headers}
        headers.update(
            {
                name: value
                for name, value in model_request_headers.items()
                if name.lower() not in protected
            }
        )
    return headers


class CopilotUpstream:
    def __init__(
        self,
        clients: SDKClients,
        token_manager: CopilotTokenManager,
        settings: AppSettings,
        *,
        interaction_id: str,
    ) -> None:
        self._clients = clients
        self._tokens = token_manager
        self._settings = settings
        self._interaction_id = interaction_id

    async def _headers(self) -> dict[str, str]:
        token = await self._tokens.get_token()
        return build_copilot_headers(
            token,
            self._settings,
            interaction_id=self._interaction_id,
        )

    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/chat/completions",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            options={"headers": await self._headers()},
            stream=stream,
        )

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._clients.anthropic.post(
            "/v1/messages",
            cast_to=httpx.Response,
            body=cast(AnthropicBody, dict(payload)),
            options={"headers": {**await self._headers(), **dict(extra_headers or {})}},
            stream=stream,
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        return await self._clients.anthropic.post(
            "/v1/messages/count_tokens",
            cast_to=httpx.Response,
            body=cast(AnthropicBody, dict(payload)),
            options={"headers": await self._headers()},
        )

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/responses",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            options={"headers": await self._headers()},
            stream=stream,
        )

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        try:
            return await self._clients.openai.post(
                "/responses",
                cast_to=httpx.Response,
                body=cast(OpenAIBody, dict(payload)),
                options={"headers": await self._headers()},
                stream=True,
            )
        except OpenAIAPIStatusError as error:
            return error.response
        except (httpx.TransportError, OpenAIAPIConnectionError) as error:
            if is_responses_headers_pending_transport_error(error):
                raise ResponsesHeadersPendingTransportError(error) from error
            raise

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/embeddings",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            options={"headers": await self._headers()},
        )