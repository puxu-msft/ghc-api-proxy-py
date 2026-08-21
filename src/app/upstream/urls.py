from app.config.settings import AppSettings
from app.model_provider.ghc_client import resolve_api_base_url
from app.upstream.ghc_settings import ghc_config_from_settings


def resolve_copilot_base_url(settings: AppSettings) -> str:
    return resolve_api_base_url(ghc_config_from_settings(settings))
