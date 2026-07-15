from collections.abc import Mapping
from uuid import uuid4

from app.config.settings import AppSettings


def resolve_copilot_base_url(settings: AppSettings) -> str:
    override = settings.upstream.ghc_api_base_url.rstrip("/")
    if override:
        return override
    account_type = settings.auth.account_type
    if account_type == "individual":
        return "https://api.githubcopilot.com"
    return f"https://api.{account_type}.githubcopilot.com"


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