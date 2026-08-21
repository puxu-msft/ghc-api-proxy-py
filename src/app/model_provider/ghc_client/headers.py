from collections.abc import Mapping
from uuid import uuid4

from app.model_provider.ghc_client.config import GhcClientConfig


def build_identity_headers(config: GhcClientConfig) -> dict[str, str]:
    """Identity headers that make the request look like the VS Code Copilot Chat client.

    Both the token exchange and ordinary requests need them; upstream rejects requests without.
    """
    return {
        "editor-version": f"vscode/{config.vscode_version}",
        "editor-plugin-version": f"copilot-chat/{config.copilot_version}",
        "user-agent": f"GitHubCopilotChat/{config.copilot_version}",
        "x-vscode-user-agent-library-version": "electron-fetch",
    }


def build_request_headers(
    token: str,
    config: GhcClientConfig,
    *,
    interaction_id: str,
    request_id: str | None = None,
    intent: str = "conversation-panel",
    vision: bool = False,
    model_request_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the model-agnostic upstream request headers.

    `model_request_headers` carries per-model extras from the catalog.
    It may not override anything set here: protocol and identity fields are owned by this library.
    """
    resolved_request_id = request_id or str(uuid4())
    headers = {
        **build_identity_headers(config),
        "Authorization": f"Bearer {token}",
        "content-type": "application/json",
        "copilot-integration-id": "vscode-chat",
        "openai-intent": intent,
        "x-github-api-version": config.api_version,
        "x-request-id": resolved_request_id,
        "X-Interaction-Id": interaction_id,
        "X-Interaction-Type": intent,
        "X-Agent-Task-Id": resolved_request_id,
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
