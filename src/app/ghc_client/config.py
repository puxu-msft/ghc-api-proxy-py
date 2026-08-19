from dataclasses import dataclass
from typing import Literal

type AccountType = Literal["individual", "business", "enterprise", "self-hosted"]

INDIVIDUAL_BASE_URL = "https://api.githubcopilot.com"
GITHUB_AUTH_BASE_URL = "https://api.github.com"


@dataclass(frozen=True, slots=True)
class GhcClientConfig:
    """All configuration this library accepts.

    Deliberately not the host's `AppSettings`: a library should not know the host's config model.

    Two hosts, not one. `api_base_url` is where inference goes; `auth_base_url` is where a GitHub
    token is exchanged for a Copilot one and where the account is described. They differ per
    deployment — an enterprise install moves both — and they used to be a settable field and a
    module constant respectively, which meant nothing could stand this library up against a local
    server: the inference calls could be redirected and the three auth calls could not.
    """

    account_type: AccountType = "individual"
    api_base_url_override: str = ""
    auth_base_url_override: str = ""
    vscode_version: str = "1.104.3"
    copilot_version: str = "0.38.0"
    api_version: str = "2025-05-01"

    @property
    def api_base_url(self) -> str:
        return resolve_api_base_url(self)

    @property
    def auth_base_url(self) -> str:
        return (self.auth_base_url_override or GITHUB_AUTH_BASE_URL).rstrip("/")


def resolve_api_base_url(config: GhcClientConfig) -> str:
    override = config.api_base_url_override.rstrip("/")
    if override:
        return override
    if config.account_type == "self-hosted":
        # A self-hosted host (e.g. msft.ghe.com) cannot be derived; it must be configured.
        raise ValueError("self-hosted accounts require an explicit api_base_url_override")
    if config.account_type == "individual":
        return INDIVIDUAL_BASE_URL
    return f"https://api.{config.account_type}.githubcopilot.com"
