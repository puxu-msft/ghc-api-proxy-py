import fnmatch
from collections.abc import Mapping, Sequence

REQUEST_FLOOR = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "proxy-authorization",
        "host",
        "content-length",
        "content-encoding",
        "accept-encoding",
        "expect",
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "via",
        "forwarded",
        "x-real-ip",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-port",
        "x-forwarded-server",
        "true-client-ip",
        "cf-connecting-ip",
        "x-client-ip",
    }
)
RESPONSE_FLOOR = frozenset(
    {
        "content-length",
        "content-encoding",
        "content-type",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "upgrade",
        "set-cookie",
        "cache-control",
        "date",
    }
)
RESPONSES_RESPONSE_HEADERS = frozenset(
    {
        "request-id",
        "x-request-id",
        "retry-after",
    }
)
RESPONSES_RATE_LIMIT_HEADERS = ("x-ratelimit-*",)


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def forward_request_headers(
    headers: Mapping[str, str],
    *,
    core: Mapping[str, str],
    strict: bool,
    blacklist: Sequence[str],
    whitelist: Sequence[str],
) -> dict[str, str]:
    core_names = {name.lower() for name in core}
    selected = {
        name: value
        for name, value in headers.items()
        if name.lower() not in REQUEST_FLOOR
        and name.lower() not in core_names
        and not name.lower().startswith(("x-github-", "openai-"))
    }
    if strict:
        selected = {name: value for name, value in selected.items() if _matches(name, whitelist)}
    else:
        selected = {
            name: value
            for name, value in selected.items()
            if not _matches(name, blacklist)
        }
    return {**selected, **core}


def forward_response_headers(
    headers: Mapping[str, str],
    *,
    strict: bool,
    blacklist: Sequence[str],
    whitelist: Sequence[str],
) -> dict[str, str]:
    selected = {
        name: value
        for name, value in headers.items()
        if name.lower() not in RESPONSE_FLOOR
    }
    if strict:
        return {name: value for name, value in selected.items() if _matches(name, whitelist)}
    return {name: value for name, value in selected.items() if not _matches(name, blacklist)}


def normalize_responses_response_headers(
    headers: Mapping[str, str],
) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() in RESPONSES_RESPONSE_HEADERS
        or _matches(name, RESPONSES_RATE_LIMIT_HEADERS)
    }


__all__ = [
    "forward_request_headers",
    "forward_response_headers",
    "normalize_responses_response_headers",
]
