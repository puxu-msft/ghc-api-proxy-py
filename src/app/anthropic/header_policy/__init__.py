import fnmatch
from collections.abc import Mapping, Sequence

REQUEST_FLOOR = frozenset(
    {
        "authorization",
        "cookie",
        "x-api-key",
        "api-key",
        "proxy-authorization",
        "host",
        "content-length",
        "content-encoding",
        "accept-encoding",
        "connection",
        "transfer-encoding",
        "upgrade",
        "via",
        "forwarded",
        "x-real-ip",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
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
        "set-cookie",
        "cache-control",
        "date",
    }
)


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


__all__ = ["forward_request_headers", "forward_response_headers"]