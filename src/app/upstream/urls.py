from app.config.settings import AppSettings


def resolve_copilot_base_url(settings: AppSettings) -> str:
    override = settings.upstream.ghc_api_base_url.rstrip("/")
    if override:
        return override
    account_type = settings.auth.account_type or "individual"
    if account_type == "individual":
        return "https://api.githubcopilot.com"
    return f"https://api.{account_type}.githubcopilot.com"