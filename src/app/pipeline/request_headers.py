"""Which of the client's request headers reach upstream.

An allowlist, for the same reason the cassette scrubber is one: naming what to remove leaks
whatever nobody thought of. Here the leak is worse than a privacy one — the upstream request
carries a Copilot Chat identity, and forwarding the client's `user-agent` or `x-stainless-*`
would replace it with something upstream refuses.

`anthropic-beta` is the load-bearing entry. Claude Code negotiates ten of them, and dropping the
header does not degrade gracefully: a body field the beta enables becomes an unrecognised field,
and upstream answers 400 rather than ignoring it.

Which is why the second function here removes flags rather than the header: the client negotiates one set of betas for a conversation, a beta is a capability of whichever model answers it, and upstream refuses the whole request over one the model does not have.
"""

from collections.abc import Mapping, Sequence

from app.pipeline.model_resolution import canonical

# Protocol negotiation the client owns. Everything else about the upstream request — identity,
# credentials, content framing — belongs to `app.model_provider.ghc_client.headers`.
FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "anthropic-beta",
        "anthropic-version",
    }
)

BETA_HEADER = "anthropic-beta"


def forwarded_client_headers(
    headers: Mapping[str, str],
    *,
    allowed: frozenset[str] = FORWARDED_REQUEST_HEADERS,
) -> dict[str, str]:
    """The subset of a client's headers that upstream should see, lowercased."""
    return {
        name.lower(): value for name, value in headers.items() if name.lower() in allowed
    }


def strip_denied_beta_flags(
    headers: Mapping[str, str],
    *,
    models: Sequence[str],
    denied_by_model: Mapping[str, Sequence[str]],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """`headers` with the flags these models must not be asked for removed, and which those were.

    Forwarding the header whole is what makes the request work at all, and it is also what breaks it: the client negotiates one set of betas for the conversation, while a beta is a property of the model that answers it. Ask `claude-sonnet-4.6` for `interleaved-thinking-2025-05-14` and upstream answers `400 invalid beta flag` — the request dies over a capability nothing in the body was using.

    **`models` is plural, and that is a decision rather than a convenience.** The capability belongs to the model that answers, so the resolved name is the semantically right one to key on — but the authoritative config keys this table on `claude-sonnet-4.6` while also mapping `claude-sonnet-4.6: claude-sonnet-5` under `model_mappings`, so no request ever resolves to the name the table is written under. Keying on the resolved name alone leaves the operator's own measured table completely inert; keying on the requested name alone leaves a client that asks for the resolved id directly unprotected. Taking the union is the only reading under which both configs do something. **Awaiting the config author's ruling** — see `.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md` §2.2.

    The removal is per-model and per-flag, not per-header: everything the operator has not named for these models travels exactly as the client spelled it. Which flags a model refuses is measured against the upstream, not derived from the name, which is why it is configuration rather than a table here.

    A header left with nothing in it is dropped rather than sent empty — the same choice `build_anthropic_beta_headers` makes when nothing is selected, and for the same reason: `anthropic-beta:` with an empty value is a third state neither side has a meaning for. A client that sent an empty value itself keeps it: this function removes flags, and there were none to remove.

    Returns a new mapping rather than editing in place, so a caller holding the client's headers for any other purpose still has what arrived. The names returned are the **configured** spellings, not the client's: they label a metric, and a client-controlled string in a label is unbounded cardinality.

    Expects header names already lowercased, which is what `forwarded_client_headers` produces and the only shape this is called with.
    """
    value = headers.get(BETA_HEADER)
    if value is None:
        return dict(headers), ()
    denied = _denied_for(models, denied_by_model)
    if not denied:
        return dict(headers), ()

    kept: list[str] = []
    removed: list[str] = []
    for token in value.split(","):
        spelling = token.strip()
        if not spelling:
            continue
        configured = denied.get(spelling.casefold())
        if configured is None:
            kept.append(spelling)
        elif configured not in removed:
            removed.append(configured)
    if not removed:
        # Byte-for-byte the value that arrived, rather than a re-joined equivalent of it. Nothing was taken away, so nothing should look different downstream either.
        return dict(headers), ()

    result = dict(headers)
    if kept:
        result[BETA_HEADER] = ",".join(kept)
    else:
        del result[BETA_HEADER]
    return result, tuple(removed)


def _denied_for(
    models: Sequence[str], denied_by_model: Mapping[str, Sequence[str]]
) -> dict[str, str]:
    """The configured flags for these models, folded spelling to configured spelling.

    `canonical` rather than string equality because the operator writes the name the way the config spells models everywhere else — `claude-sonnet-4.6` — while what arrives here is whatever the route resolved to. A map that only fired on an exact match would be silently inert for the one spelling the example config uses.

    Every canonically equal key contributes, rather than the first one found: `claude-sonnet-4.6` and `claude-sonnet-4-6` are one model, and letting the second be dropped would make the flags under it disappear without anything saying so.
    """
    wanted = {canonical(name) for name in models if name}
    denied: dict[str, str] = {}
    for key, flags in denied_by_model.items():
        if canonical(key) not in wanted:
            continue
        for flag in flags:
            spelling = flag.strip()
            if spelling:
                denied.setdefault(spelling.casefold(), spelling)
    return denied
