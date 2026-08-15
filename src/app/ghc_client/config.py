from dataclasses import dataclass
from typing import Literal

type AccountType = Literal["individual", "business", "enterprise"]

INDIVIDUAL_BASE_URL = "https://api.githubcopilot.com"


@dataclass(frozen=True, slots=True)
class GhcClientConfig:
    """All configuration this library accepts.

    Deliberately not the host's `AppSettings`: a library should not know the host's config model.
    """

    account_type: AccountType = "individual"
    base_url_override: str = ""
    vscode_version: str = "1.104.3"
    copilot_version: str = "0.38.0"
    api_version: str = "2025-05-01"

    @property
    def base_url(self) -> str:
        return resolve_base_url(self)


def resolve_base_url(config: GhcClientConfig) -> str:
    override = config.base_url_override.rstrip("/")
    if override:
        return override
    if config.account_type == "individual":
        return INDIVIDUAL_BASE_URL
    return f"https://api.{config.account_type}.githubcopilot.com"
