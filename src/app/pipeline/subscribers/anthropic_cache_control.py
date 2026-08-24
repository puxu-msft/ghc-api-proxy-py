"""Which keys a `cache_control` object may carry on the way to an Anthropic Messages upstream.

Copilot's Anthropic endpoint validates `cache_control` with a strict schema: its words are `Extra inputs are not permitted`, and **any** key it does not know kills the whole request. Claude Code sends `{"type": "ephemeral", "scope": …}` — the `scope` field the `prompt-caching-scope-2026-01-05` beta introduces — and every request carrying one comes back 400.

Measured 2026-08-24 against the live enterprise upstream, `claude-opus-5`, positive control first, the whole matrix run twice with identical results (`exp/260824-beta-and-cache-control-probe/`):

- `{"type": "ephemeral"}` → 200, and `{"type": "ephemeral", "ttl": "1h"}` → 200 with or without its own beta. So `ttl` is kept: removing it would be a pure loss.
- `{"type": "ephemeral", "scope": "organization"}` → 400 `system.1.cache_control.ephemeral.scope: Extra inputs are not permitted`, and the same on a message block (`messages.0.content.0.text.cache_control…`) and on a tool (`tools.0.custom.cache_control…`). Three separate schemas upstream, so all three have to be walked.
- **Sending the enabling beta does not help.** The same body with `anthropic-beta: prompt-caching-scope-2026-01-05` comes back with an identical error, while that flag *on its own* — with a body that does not use it — is accepted with 200. The gateway takes the beta and the backend behind it still refuses the field it enables. That measurement is why this strips the field instead of adding a header, which is the opposite repair and the more natural first guess.

**A whitelist rather than a list of known-bad keys.** Upstream's schema is strict, so a blacklist would need updating ahead of every field Anthropic adds, and missing one takes the whole proxy down for that client. Getting the whitelist wrong costs an optimisation upstream would have accepted. The two are not symmetric.

**This is about keys, not about breakpoints — and it only runs when the operator asks for it.** Where the markers go, how many there are, and whether the proxy or the client owns them is what `hook_fix_anthropic_request.cache_control` answers in four modes. This pass implements three of them: `passthrough` (the default) does nothing at all, `sanitize` applies the whitelist, `disabled` removes every marker. `proxied` is rejected at startup because its injection half does not exist.

**The default does not sanitise, and that is a ruling rather than an omission.** An earlier version ran the whitelist under every mode, arguing that removing a key upstream cannot read does not move a breakpoint and so does not contradict `passthrough`'s "as-is". An independent review named that for what it was — a user-defined default rewritten by an argument the same author had written — and the user ruled on 2026-08-24 that `passthrough` is literal. A deployment whose clients send `cache_control.scope` therefore needs `cache_control: sanitize` in its config; under the default those requests get upstream's 400.

Spec: `.dev/docs/anthropic-direct-request-shape/spec.md` §7.
"""

import logging
from typing import Any, cast

from app.config.schema import CacheControlMode
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.semantic import Loss, LossCode

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:anthropic-cache-control-vocabulary"

# How the request's own `cache_control` is spelled in a loss path. It has no index and no block, so it needs a name of its own rather than an empty prefix that would render as `.cache_control.scope`.
TOP_LEVEL = "(request)"

# What upstream accepts inside a `cache_control`, measured rather than derived. `type` because a marker without it is not a marker; `ttl` because it was sent and accepted, so removing it would cost a longer cache for nothing.
ACCEPTED_FIELDS = frozenset({"type", "ttl"})

# Same channel `anthropic_thinking` writes to, and for the same reason: `observability/request_trace.py` reads this key, so a loss recorded here reaches the console line and the record, while one recorded anywhere else reaches nobody.
_REQUEST_LOSSES = "conversion_losses"


def _record_loss(context: RequestContext, detail: str) -> None:
    recorded = context.extras.get(_REQUEST_LOSSES)
    if not isinstance(recorded, list):
        recorded = []
        context.extras[_REQUEST_LOSSES] = recorded
    cast(list[Any], recorded).append(
        Loss(LossCode.CACHE_CONTROL_FIELD_NOT_CARRIED, detail)
    )


def _prune(entry: dict[str, Any], path: str, accepted: frozenset[str]) -> tuple[str, ...]:
    """Remove the keys not in `accepted` from `entry`'s marker, returning their names.

    `accepted` carries the mode: the whitelist under `sanitize`, and empty under `disabled` — where every key is unacceptable, nothing is kept, and the branch below removes the marker outright. One rule, two modes, rather than a second walk that could drift from this one.

    In place, because by `attempt.prepare` the payload is the outbound body rather than the client's own — `repair_tool_pairs` has already edited `messages` in place a step earlier, and rebuilding here would only make this one pass look careful about something the chain does not preserve.

    A marker left with nothing but unknown keys is removed whole rather than sent as `{}`. That case needs `type` to have been absent, which no client is known to do; an empty marker says nothing, and whether upstream accepts one has not been measured, so the shape that is known to be safe is no marker at all.
    """
    marker = entry.get("cache_control")
    if not isinstance(marker, dict):
        # Absent, or present as something that is not an object — `null`, a string. Left for upstream to name: this pass knows which *keys* are acceptable, not what a non-object marker was meant to be.
        return ()
    fields = cast(dict[str, Any], marker)
    removed = tuple(sorted(name for name in fields if name not in accepted))
    if not removed:
        return ()
    kept = {name: value for name, value in fields.items() if name in accepted}
    if kept:
        entry["cache_control"] = kept
    else:
        del entry["cache_control"]
    logger.debug("removed cache_control %s at %s", ",".join(removed), path)
    return removed


# Block types whose own `content` is another list of cacheable blocks, per the Anthropic request schema. Dispatched by type rather than recursed blindly: an unconditional walk would descend into `tool_use.input`, a tool's JSON Schema, and ordinary tool output, where a key that happens to be spelled `cache_control` is the client's data and deleting it would edit their payload.
_NESTED_CONTENT_BLOCKS = frozenset({"tool_result", "search_result"})


def _prune_blocks(blocks: Any, path: str, accepted: frozenset[str]) -> list[tuple[str, str]]:
    """Every block in a content list, and the nested lists the schema says are cacheable too."""
    if not isinstance(blocks, list):
        # A string `content` or `system` carries no marker at all — there is nowhere to put one.
        return []
    found: list[tuple[str, str]] = []
    for index, block in enumerate(cast(list[Any], blocks)):
        if not isinstance(block, dict):
            continue
        entry = cast(dict[str, Any], block)
        where = f"{path}.{index}"
        found.extend((where, name) for name in _prune(entry, where, accepted))

        kind = entry.get("type")
        if kind in _NESTED_CONTENT_BLOCKS:
            found.extend(_prune_blocks(entry.get("content"), f"{where}.content", accepted))
        elif kind == "document":
            # Only the `ContentBlockSourceParam` branch nests; the base64/url/file/text sources carry no blocks.
            source = entry.get("source")
            if isinstance(source, dict):
                found.extend(
                    _prune_blocks(
                        cast(dict[str, Any], source).get("content"),
                        f"{where}.source.content",
                        accepted,
                    )
                )
    return found


async def prune_cache_control_fields(
    context: RequestContext, *, mode: CacheControlMode = "sanitize"
) -> None:
    """Apply the operator's `cache_control` mode to the outbound body.

    **The mode is the user's decision and this function does not second-guess it.** `config.example.yaml` defines the four spellings and the user ruled on 2026-08-24 that `passthrough` means what it says: forward the client's markers byte for byte, including keys this upstream refuses. An earlier version of this pass sanitised under every mode on the argument that removing an unknown key does not move a breakpoint — an independent review called that what it was, a default rewritten without the authority to rewrite it, and the user settled it the other way.

    So a deployment whose clients send `cache_control.scope` needs `cache_control: sanitize` written in its config; under the default `passthrough` those requests reach upstream as the client wrote them and upstream answers 400. That is the ruled behaviour, not an oversight.

    | mode | what happens here |
    |---|---|
    | `passthrough` (default) | nothing at all |
    | `sanitize` | every marker keeps only the keys upstream accepts |
    | `disabled` | every marker is removed outright |
    | `proxied` | rejected at startup; the injection half is not implemented |

    Reads the route rather than the inbound format, for the reason its siblings give: what upstream accepts is a property of the endpoint being spoken to, so a request translated *into* Anthropic shape belongs here too and one translated *out* of it does not.

    Registered after `builtin:server-tool-capability` by an explicit constraint. That pass rewrites a server-tool result into a text block and **deliberately carries its `cache_control` across** (`server_tools.py:124-129`, so a breakpoint keeps marking the same boundary) — so it can put a marker this has already walked past back into the body. Running after it is what makes "everywhere they can appear" true rather than true of the shape that arrived.

    Idempotent: a second pass over a body this already pruned finds only accepted keys and records nothing, which matters because `attempt.prepare` fires once per attempt and a retry re-runs it over the payload the last pass edited.

    Not exempt on the counting leg. A count taken from a body carrying a field that would have made the real request 400 is a count of a request nobody could send.
    """
    if mode == "passthrough":
        # The ruled default. Not even a walk: the client's body is the outbound body here.
        return
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return

    payload = context.payload
    found: list[tuple[str, str]] = []

    # The top level first, and it is the one with no block to hang off: `cache_control` on the request itself means "put a marker on the last cacheable block". Nothing else here would reach it, which is exactly why it was the position this pass originally missed.
    accepted = ACCEPTED_FIELDS if mode == "sanitize" else frozenset[str]()

    found.extend((TOP_LEVEL, name) for name in _prune(payload, TOP_LEVEL, accepted))

    found.extend(_prune_blocks(payload.get("system"), "system", accepted))

    messages = payload.get("messages")
    if isinstance(messages, list):
        for index, message in enumerate(cast(list[Any], messages)):
            if not isinstance(message, dict):
                continue
            found.extend(
                _prune_blocks(
                    cast(dict[str, Any], message).get("content"),
                    f"messages.{index}.content",
                    accepted,
                )
            )

    tools = payload.get("tools")
    if isinstance(tools, list):
        for index, tool in enumerate(cast(list[Any], tools)):
            if not isinstance(tool, dict):
                continue
            where = f"tools.{index}"
            found.extend(
                (where, name) for name in _prune(cast(dict[str, Any], tool), where, accepted)
            )

    if not found:
        return

    # One loss per marker rather than one per pass, and each carries its path. A reader of the record is asking *which* breakpoints were altered — `scope` decides how widely a cached prefix is shared, so the answer differs per position — and a single entry saying "3 markers" cannot answer that.
    #
    # **The two modes say different things and must not share a sentence.** Under `sanitize` a key is gone because upstream refuses it, and naming the key is what a reader needs. Under `disabled` the whole marker is gone because the operator asked for it — upstream refuses nothing here, and a record claiming it does would send the next reader looking for an upstream problem that does not exist.
    if mode == "disabled":
        for where in dict.fromkeys(path for path, _ in found):
            _record_loss(context, f"{where}.cache_control removed; disabled by configuration")
        logger.info(
            "%s: removed every cache_control (%d marker(s)); disabled by configuration",
            SUBSCRIBER_ID,
            len(dict.fromkeys(path for path, _ in found)),
        )
        return

    for where, name in found:
        _record_loss(context, f"{where}.cache_control.{name} not carried; upstream refuses it")

    # INFO rather than debug: this changes what the cache does, and an operator wondering why prompt caching behaves differently through the proxy should not have to turn on debug logging to find out. It is also not routine noise: a client that sends only keys upstream knows never reaches this line. One line for the request, with the per-marker detail in the record above.
    logger.info(
        "%s: removed cache_control %s from %d marker(s)",
        SUBSCRIBER_ID,
        ",".join(sorted({name for _, name in found})),
        len(found),
    )
