from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

type AccountType = Literal["individual", "business", "enterprise", "self-hosted"]

INDIVIDUAL_BASE_URL = "https://api.githubcopilot.com"
GITHUB_AUTH_BASE_URL = "https://api.github.com"
GITHUB_WEB_BASE_URL = "https://github.com"
# The path a self-hosted GitHub Enterprise Server answers its REST API on. Its presence is what distinguishes that deployment from github.com and from a residency tenant, both of which answer on a dedicated `api.` host with no path at all.
ENTERPRISE_SERVER_API_PATH = "/api/v3"


@dataclass(frozen=True, slots=True)
class GhcClientConfig:
    """All configuration this library accepts.

    Deliberately not the host's `AppSettings`: a library should not know the host's config model.

    Two hosts, not one. `api_base_url` is where inference goes; `auth_base_url` is where a GitHub token is exchanged for a Copilot one and where the account is described. They differ per deployment — an enterprise install moves both — and they used to be a settable field and a module constant respectively, which meant nothing could stand this library up against a local server: the inference calls could be redirected and the three auth calls could not.

    Three roles, still two fields. `github_web_base_url` — the OAuth origin Device Flow posts to — is *derived* from `auth_base_url` rather than configured, because a tenant's two hosts are one fact spelled twice, and asking an operator to write both invents a third source of truth for it. Same reason `account_type` is not a key; see `resolve_provider_base_urls`.
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

    @property
    def github_web_base_url(self) -> str:
        """Raises `ValueError` when the auth host is not one Device Flow can be reached through."""
        return resolve_github_web_base_url(self.auth_base_url)


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


def resolve_github_web_base_url(auth_base_url: str) -> str:
    """The OAuth origin Device Flow posts to, derived from the host that answers the GitHub REST API.

    Three mappings and no fourth: `https://api.github.com` to `https://github.com`; a data-residency tenant's `https://api.<tenant>.ghe.com` to `https://<tenant>.ghe.com`; and a self-hosted Enterprise Server's `https://<host>/api/v3` to `https://<host>`.

    **The `/api/v3` suffix is what tells the third apart from the first two**, which is why it is the only path this function accepts. GitHub.com and a residency tenant answer the REST API on a dedicated `api.` host with nothing after it; an Enterprise Server answers it on the same host the browser uses, under a path.

    **Anything else raises rather than falling back to github.com**, which is the whole point. Device Flow reached github.com unconditionally until 2026-08-28 because the two URLs were module constants with no injection point, so a tenant deployment logged in against dotcom and stored a token its own upstream would not honour — a wrong host that produced a *successful*-looking login. Substituting github.com for a host we could not read would reinstate exactly that: a silent wrong answer where a refusal belongs.

    The cost is accepted knowingly. `auth_base_url` also exists so this library can be stood up against a local server, and no local host derives an origin — but that only reaches `auth`, not `logout`, which needs a token file and never asks where the OAuth endpoints are. Spec `.dev/docs/ghe-device-flow/spec.md` §3.2, §3.3.

    A multi-label tenant is allowed. Not because it is known to work — public documentation only ever shows one label — but because refusing a shape we cannot show to be illegal would dress "we did not find it documented" up as "the server rejects it". A tenant that does not exist fails loudly at DNS instead, which names the problem.
    """
    raw = auth_base_url.rstrip("/")
    try:
        parts = urlsplit(raw)
        # Read inside the guard: `urlsplit` defers both the port cast and the IPv6 bracket check to attribute access, and each raises a `ValueError` of its own wording — one that says nothing about which shapes this function accepts. §3.3 requires every refusal to carry both what arrived and what was expected, so those are rewritten rather than allowed through.
        hostname, port = parts.hostname or "", parts.port
    except ValueError as error:
        raise ValueError(_undecodable(auth_base_url)) from error
    if port not in (None, 443):
        raise ValueError(_undecodable(auth_base_url))
    # Presence, not truthiness. Asking whether `parts.username` is set asks whether userinfo carried a *value*, and `https://@api.github.com` carries an empty one — the `@` sits in the authority while the field reads as absent, so a per-field check waves it through. Comparing the input against the origin it would rebuild asks the question actually meant: is this nothing but a host, at most its default port, and at most the one path that identifies an Enterprise Server? That comparison covers scheme, userinfo, query, fragment and every empty delimiter at once, and cannot be walked past by a component nobody thought to enumerate.
    origin = f"https://{hostname}" if port is None else f"https://{hostname}:{port}"
    if raw.lower() == origin + ENTERPRISE_SERVER_API_PATH:
        # Self-hosted: the REST API hangs off the same host the browser uses, so that host *is* the OAuth origin. Rebuilt from the hostname rather than returned as `origin`, so an explicit `:443` normalises away here exactly as it does on the other two branches — otherwise the same deployment would produce two spellings of one origin depending on how its config was written.
        return urlunsplit(("https", hostname, "", "", ""))
    if raw.lower() != origin:
        raise ValueError(_undecodable(auth_base_url))
    if hostname == "api.github.com":
        web_hostname = "github.com"
    elif hostname.startswith("api.") and hostname.endswith(".ghe.com"):
        web_hostname = hostname.removeprefix("api.")
        # An empty label is no tenant. Comparing the whole string against `ghe.com` missed `api..ghe.com`, which derived `https://.ghe.com` and left the failure to DNS.
        if web_hostname == "ghe.com" or any(
            label == "" for label in web_hostname.removesuffix(".ghe.com").split(".")
        ):
            raise ValueError(
                f"cannot derive the Device Flow OAuth origin from auth_base_url {auth_base_url!r}: a data-residency host must name a tenant, as in https://api.<tenant>.ghe.com"
            )
    else:
        raise ValueError(_undecodable(auth_base_url))
    return urlunsplit(("https", web_hostname, "", "", ""))


def _undecodable(auth_base_url: str) -> str:
    return f"cannot derive the Device Flow OAuth origin from auth_base_url {auth_base_url!r}: expected https://api.github.com, https://api.<tenant>.ghe.com, or a self-hosted https://<host>/api/v3"
