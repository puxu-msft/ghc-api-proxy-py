"""Which of the client's request headers reach upstream.

Two stages, because the two questions are answered at different moments.

**The floor**, applied in `build_context` before anything downstream can hold the result: credentials, the proxy's own identity, hop-by-hop fields and the forwarded chain are removed unconditionally. `REQUEST_FLOOR` in `app.anthropic.header_policy` is the list, and it matches the reference implementation's `SENSITIVE_DENYLIST` entry for entry. `message-format-reshape.md` names a shorter list — `Forwarded` chain, `Cookie`, `X-Api-Key`, `Host`, `Content-Length`, `Content-Encoding`, `Accept-Encoding` — and every one of those is inside the floor. What the document's summary leaves out is `authorization` itself, which the reference implementation guards twice.

**The path policy**, applied in `shape_request` once routing has decided: the direct path forwards by blacklist, the translation path by whitelist, exactly as that document says. Its whitelist is empty today, so a translated request forwards nothing of the client's — `anthropic-beta` included, which the Anthropic-to-Responses leg had been sending to an endpoint that has no betas.

Splitting them is what lets the floor keep its promise. Routing has not happened at parse time, so a single path-aware filter there would be guessing; a single filter after routing would leave the client's credentials on the context in between.

`anthropic-beta` is the load-bearing entry on the direct path. Claude Code negotiates ten of them, and dropping the header does not degrade gracefully: a body field the beta enables becomes an unrecognised field, and upstream answers 400 rather than ignoring it. Which is why the last function here removes flags rather than the header: a beta is a capability of whichever model answers, and upstream refuses the whole request over one that model does not have.
"""

import re
from collections.abc import Mapping, Sequence

from app.anthropic.header_policy import forward_request_headers

BETA_HEADER = "anthropic-beta"

# The direct path's blacklist, beyond the floor. Empty, and that is the finding rather than an omission: every entry `message-format-reshape.md` lists for the direct path is already in `REQUEST_FLOOR`, so the floor alone realises the document's list. Kept as a named seam because the document's own TODO says those entries came from `copilot-api-js` and their reasons are not yet understood — when one of them turns out to belong here rather than in the floor, this is where it goes.
DIRECT_PATH_BLACKLIST: tuple[str, ...] = ()

# The translation path's whitelist. `message-format-reshape.md` writes it as "(暂无)" and means it: a translated request is not a forwarded one, so a header negotiated against the Anthropic wire format has no standing on the endpoint that actually answers.
TRANSLATED_PATH_WHITELIST: tuple[str, ...] = ()


def forwarded_client_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """The floor, lowercased. Everything a client may still be carrying after this is safe to hold.

    Lowercased here so that every later stage — the path policy, the beta-flag strip, the send site — can look a header up by one spelling. HTTP header names are case-insensitive and clients do not agree on a case; `Anthropic-Beta` and `anthropic-beta` reaching different code paths is the kind of split that shows up as a header silently not being acted on.
    """
    return {
        name.lower(): value
        for name, value in forward_request_headers(
            headers, core={}, strict=False, blacklist=(), whitelist=()
        ).items()
    }


def apply_path_header_policy(
    headers: Mapping[str, str], *, translated: bool
) -> dict[str, str]:
    """The client headers this path may forward, per `message-format-reshape.md`.

    Blacklist for the direct path, whitelist for the translation path. The floor has already run, so what arrives here is the client's own protocol negotiation rather than anything sensitive; this decides how much of that negotiation still means something once the request stops being the one the client wrote.
    """
    return forward_request_headers(
        headers,
        core={},
        strict=translated,
        blacklist=DIRECT_PATH_BLACKLIST,
        whitelist=TRANSLATED_PATH_WHITELIST,
    )


def compile_beta_flag_denials(
    denied_by_model: Mapping[str, Sequence[str]],
) -> tuple[tuple[re.Pattern[str], tuple[str, ...]], ...]:
    """The configured table as compiled patterns, in the order the operator wrote them.

    Compiled once at startup rather than per request, for the reason `compile_supported` gives about the other model-pattern table in this config: left uncompiled, a pattern that does not compile raises from inside whichever request first reached it rather than from the config that holds it — and catching it per request would turn a typo into a model whose flags are silently never stripped, which is the exact failure this table exists to prevent.

    **An entry is a regular expression, including the ones that look like plain model ids.** `.` is a wildcard, so `claude-sonnet-4.6` also claims `claude-sonnet-4-6` — here that happens to be wanted, since the two are the same model under the config's own spelling rules, but it is an accident of the syntax and not a folding rule. To pin an id exactly, escape it: `claude-sonnet-4\\.6`.

    `fullmatch` at the call site, not `search`, so `claude-sonnet-4.6` does not also claim `claude-sonnet-4.6-experimental`. Order is preserved and the first match wins, so a specific entry placed above a broad one is how an operator says which of the two they meant.
    """
    compiled: list[tuple[re.Pattern[str], tuple[str, ...]]] = []
    for pattern, flags in denied_by_model.items():
        try:
            expression = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"strip_anthropic_beta_flags key {pattern!r} is not a valid regular expression: {exc}"
            ) from exc
        compiled.append(
            (expression, tuple(flag.strip() for flag in flags if flag.strip()))
        )
    return tuple(compiled)


def strip_denied_beta_flags(
    headers: Mapping[str, str],
    *,
    model: str,
    denials: Sequence[tuple[re.Pattern[str], tuple[str, ...]]],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """`headers` with the flags this model must not be asked for removed, and which those were.

    Forwarding the header whole is what makes the request work at all, and it is also what breaks it: the client negotiates one set of betas for the conversation, while a beta is a property of the model that answers it. Ask `claude-sonnet-4.6` for `interleaved-thinking-2025-05-14` and upstream answers `400 invalid beta flag` — the request dies over a capability nothing in the body was using.

    `model` is the model the attempt is actually sent to, not the name the client asked for. A capability belongs to the model that answers, so an alias is looked through rather than matched on — which does mean a table keyed on an alias `model_mappings` maps away never fires, and that is the config's own question to answer rather than something to paper over here.

    The removal is per-model and per-flag, not per-header: everything the operator has not named for this model travels exactly as the client spelled it. Which flags a model refuses is measured against the upstream, not derived from the name, which is why it is configuration rather than a table here.

    A header left with nothing in it is dropped rather than sent empty — the same choice `build_anthropic_beta_headers` makes when nothing is selected, and for the same reason: `anthropic-beta:` with an empty value is a third state neither side has a meaning for. A client that sent an empty value itself keeps it: this function removes flags, and there were none to remove.

    Returns a new mapping rather than editing in place, so a caller holding the client's headers for any other purpose still has what arrived. The names returned are the **configured** spellings, not the client's: they label a metric, and a client-controlled string in a label is unbounded cardinality.

    Expects header names already lowercased, which is what `forwarded_client_headers` produces and the only shape this is called with.
    """
    value = headers.get(BETA_HEADER)
    if value is None:
        return dict(headers), ()
    denied = _denied_for(model, denials)
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
    model: str, denials: Sequence[tuple[re.Pattern[str], tuple[str, ...]]]
) -> dict[str, str]:
    """The first matching entry's flags, folded spelling to configured spelling.

    First match rather than a union of every match: entries are ordered, and an operator who writes a specific model above a catch-all is saying which of the two applies. Merging them would make the narrow entry unable to *reduce* what the broad one takes away.
    """
    for expression, flags in denials:
        if not expression.fullmatch(model):
            continue
        denied: dict[str, str] = {}
        for flag in flags:
            denied.setdefault(flag.casefold(), flag)
        return denied
    return {}
