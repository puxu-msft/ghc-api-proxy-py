"""Maps `AppSettings` onto the `app.ghc_client` configuration.

Kept in its own module to avoid an import cycle.
Both `urls` and `copilot` need this mapping.
`copilot` depends on `upstream.client`, which depends on `urls`.
"""

from app.config.settings import AppSettings
from app.ghc_client import GhcClientConfig


def ghc_config_from_settings(settings: AppSettings) -> GhcClientConfig:
    versions = settings.headers
    return GhcClientConfig(
        account_type=settings.auth.account_type or "individual",
        base_url_override=settings.upstream.ghc_api_base_url,
        vscode_version=versions.vscode_version,
        copilot_version=versions.copilot_version,
        api_version=versions.api_version,
    )
