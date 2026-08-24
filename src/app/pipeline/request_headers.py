"""Which of the client's request headers reach upstream.

Two stages, because the two questions are answered at different moments.

**The floor**, applied in `build_context` before anything downstream can hold the result: credentials, the proxy's own identity, hop-by-hop fields and the forwarded chain are removed unconditionally. `REQUEST_FLOOR` in `app.anthropic.header_policy` is the list, and it matches the reference implementation's `SENSITIVE_DENYLIST` entry for entry. `message-format-reshape.md` names a shorter list — `Forwarded` chain, `Cookie`, `X-Api-Key`, `Host`, `Content-Length`, `Content-Encoding`, `Accept-Encoding` — and every one of those is inside the floor. What the document's summary leaves out is `authorization` itself, which the reference implementation guards twice.

**The path policy**, applied in `shape_request` once routing has decided: the direct path forwards by blacklist, the translation path by whitelist, exactly as that document says. Its whitelist is empty today, so a translated request forwards nothing of the client's — `anthropic-beta` included, which the Anthropic-to-Responses leg had been sending to an endpoint that has no betas.

Splitting them is what lets the floor keep its promise. Routing has not happened at parse time, so a single path-aware filter there would be guessing; a single filter after routing would leave the client's credentials on the context in between.

`anthropic-beta` is the load-bearing entry on the direct path. Claude Code negotiates ten of them, and dropping the header does not degrade gracefully: a body field the beta enables becomes an unrecognised field, and upstream answers 400 rather than ignoring it. Which is why the last functions here remove flags rather than the header.

**Two of them, because a flag can be refused for two unrelated reasons and only one of them is the operator's business.** `strip_denied_beta_flags` answers "this model does not have that capability" — Anthropic's own `400 invalid beta flag`, per model, from a table the user writes. `strip_gateway_unsupported_betas` answers "this deployment has never heard of that name" — the Copilot gateway's `unsupported beta header(s)`, refused before any model sees the request, from a built-in list of measurements. Merging them would give one table two meanings and put our derivations inside the user's decision.
"""

import re
from collections.abc import Mapping, Sequence

from app.anthropic.header_policy import forward_request_headers

BETA_HEADER = "anthropic-beta"

# Betas this Copilot gateway does not know the *name* of, which is a different question from the one `strip_denied_beta_flags` below answers.
#
# **Two layers, two vocabularies.** A capability beta is refused by the model, in Anthropic's own envelope, with `400 invalid beta flag`; that is what the operator's per-model table is for. These are refused by the Copilot gateway in *its* envelope — `{"error": {"message": "unsupported beta header(s): …", "code": "invalid_request_body"}}` — before any model sees the request, and the refusal has nothing to do with which model was asked for. Measured 2026-08-24 against `api.enterprise.githubcopilot.com`: `tool-search-tool-2025-10-19` is refused while `tool-search-tool-2025-11-19` is accepted, one digit apart. That is a vocabulary lookup, not a capability judgement.
#
# **Why built in rather than configured.** It is an upstream fact rather than an operator preference, so it belongs where the other measured upstream facts live — the same standing `normalize_context_management` has. It is deliberately *not* merged into `strip_anthropic_beta_flags`: that table is the user's, spec §8 and §9 A-4 say its contents are the user's to rule on, and seeding it with built-in defaults would put our derivation inside their decision. A `.*` key would work mechanically and mislead permanently.
#
# **Removing these is measured safe, which is the whole reason this is allowed to be unconditional.** `request_headers.py` warns that dropping a beta does not degrade gracefully — the body field it enabled becomes an unrecognised field and upstream answers 400 instead of ignoring it. For `tool-search-tool-2025-10-19` that warning does not hold, and it was checked rather than assumed across the feature's whole lifecycle: `tools[].defer_loading` mixed true/false, a `tool_search_tool_regex_20251119` server tool, and the second-round `tool_result` carrying `{"type": "tool_reference"}` blocks were each sent with **no** beta at all and each answered 200. So the flag can go and the body travels as the client wrote it.
#
# **When this list goes stale it fails cheap.** If the gateway later learns `tool-search-tool-2025-10-19`, we keep removing a flag upstream would now have taken — and by the paragraph above the body does not need it, so the cost is a negotiation nobody was using. The reverse, leaving it in, kills every request from a client that sends it. `output-128k-2025-02-19` is here on the same measurement; unlike its neighbour there is no observation of a client sending it, so it costs nothing until one does.
#
# Evidence: `.dev/docs/anthropic-direct-request-shape/reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md` §3 and §4.
GATEWAY_UNSUPPORTED_BETAS: tuple[str, ...] = (
    "tool-search-tool-2025-10-19",
    "output-128k-2025-02-19",
)

# Folded once at import rather than per request. Same shape `_denied_for` builds for the configured table, so both feed `_remove_flags` the same way: casefolded spelling to the spelling worth reporting.
_GATEWAY_DENIED: dict[str, str] = {
    flag.casefold(): flag for flag in GATEWAY_UNSUPPORTED_BETAS
}

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

    The mechanics of the removal itself — an emptied header being dropped rather than sent blank, a new mapping rather than an edit in place, and which spelling comes back — belong to `_remove_flags`, which this shares with `strip_gateway_unsupported_betas`.

    Expects header names already lowercased, which is what `forwarded_client_headers` produces and the only shape this is called with.
    """
    denied = _denied_for(model, denials)
    if not denied:
        return dict(headers), ()
    return _remove_flags(headers, denied)


def strip_gateway_unsupported_betas(
    headers: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """`headers` with the flags this Copilot gateway does not recognise removed, and which those were.

    Unconditional and not keyed on the model, because the refusal is not the model's: the gateway answers `unsupported beta header(s)` in its own envelope before the request reaches one. See `GATEWAY_UNSUPPORTED_BETAS` for what is in the list, why it is built in rather than configured, and the measurements that make removing these safe.

    Runs alongside `strip_denied_beta_flags` rather than instead of it. A request can hit both — a name this deployment has never heard of, and a capability the answering model lacks — and folding them into one table would make the union unable to say which kind of refusal it was preventing.
    """
    return _remove_flags(headers, _GATEWAY_DENIED)


def _remove_flags(
    headers: Mapping[str, str], denied: Mapping[str, str]
) -> tuple[dict[str, str], tuple[str, ...]]:
    """The shared removal, given a fold from a flag's casefolded spelling to the spelling to report.

    A header left with nothing in it is dropped rather than sent empty — the same choice `build_anthropic_beta_headers` makes when nothing is selected, and for the same reason: `anthropic-beta:` with an empty value is a third state neither side has a meaning for. A client that sent an empty value itself keeps it: this removes flags, and there were none to remove.

    Returns a new mapping rather than editing in place, so a caller holding the client's headers for any other purpose still has what arrived. The names returned are the **configured** spellings, not the client's: they label a metric, and a client-controlled string in a label is unbounded cardinality.
    """
    value = headers.get(BETA_HEADER)
    if value is None:
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
