"""Which of the client's request headers reach upstream.

An allowlist, for the same reason the cassette scrubber is one: naming what to remove leaks
whatever nobody thought of. Here the leak is worse than a privacy one — the upstream request
carries a Copilot Chat identity, and forwarding the client's `user-agent` or `x-stainless-*`
would replace it with something upstream refuses.

`anthropic-beta` is the load-bearing entry. Claude Code negotiates ten of them, and dropping the
header does not degrade gracefully: a body field the beta enables becomes an unrecognised field,
and upstream answers 400 rather than ignoring it.
"""

from collections.abc import Mapping

# Protocol negotiation the client owns. Everything else about the upstream request — identity,
# credentials, content framing — belongs to `app.ghc_client.headers`.
FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "anthropic-beta",
        "anthropic-version",
    }
)


def forwarded_client_headers(
    headers: Mapping[str, str],
    *,
    allowed: frozenset[str] = FORWARDED_REQUEST_HEADERS,
) -> dict[str, str]:
    """The subset of a client's headers that upstream should see, lowercased."""
    return {
        name.lower(): value for name, value in headers.items() if name.lower() in allowed
    }
