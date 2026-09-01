"""Reasoning item ids this proxy minted, removed from the body it is about to send back to upstream.

**Off by default. It is a compatibility reshape, not part of the native leg** — `.dev/docs/direct-passthrough/spec.md` §2.7 requires such a thing to be a declared, optional contract that is never called verbatim or native, and §6.5 is the clause this implements. `hook_fix_responses_request.repair_minted_reasoning_ids` is the switch.

**What it repairs.** `encrypted_content` is bound to the item id upstream issued it under, and upstream verifies that binding when the item comes back. Before `1fb37cd` the translating Responses leg minted its own ids — `ResponsesFramer._item_id` returns `f"{prefix}_{response_id}_{output_index}"` over a `uuid4` — while carrying upstream's seal, so the pair a client stored was self-contradictory. That production leg is gone; the pairs already written into clients' rollout histories are not. A client replaying its history sends them back every turn and is refused every turn, and **upgrading this proxy does not repair them** — they live in the client's store, not here. GitHub issue #4.

**Why the id goes and the seal stays.** This proxy did not keep upstream's original item id and cannot rebuild it from anything it still holds — the reasoning carrier stores `encrypted_content` and nothing else — so rewriting the id to the correct value is not available. Measured 2026-09-01 against the live upstream: that seal was refused under each of three different mismatched ids, with an error naming the item-id mismatch, and the same body with no `id` at all was accepted. Removing `encrypted_content` instead would also be accepted and would throw the turn's reasoning away; this drops the label, not the content.

**Why the shape is pinned this tightly.** `rs_` followed by anything and a number is enough to recognise the defect on this upstream, where item ids are unprefixed base64 — and the user ruled against it, because `rs_` is also how OpenAI spells a reasoning item and a looser pattern risks stripping an id some upstream legitimately issued. So the pattern is written to the text `_item_id` can actually produce on the known production path: a lowercase RFC-4122 version-4 UUID and a decimal index with no leading zeros.
"""

import logging
import re
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:repair-minted-reasoning-ids"

# `f"rs_{response_id}_{output_index}"` as the known production path spells it: `response_id` is `RequestContext.id`, which `inference.py` passes verbatim and which defaults to `str(uuid4())`; the index is `str()` of a non-negative `int`.
#
# **Version and variant are pinned, and the index refuses a leading zero, because a looser pattern is a wider set than this proxy can emit.** `uuid4()` always writes `4` as the first character of the third group and one of `89ab` as the first of the fourth, and `str(0)` is never `00` — so `rs_00000000-0000-1000-8000-000000000000_0` and `rs_<uuid>_00` are both things only some *other* author could have written, and stripping their ids would be the collision the narrow ruling exists to avoid.
_MINTED_REASONING_ID = re.compile(
    r"rs_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}_(?:0|[1-9][0-9]*)\Z"
)


def _is_minted_sealed_reasoning(item: Any) -> bool:
    """Whether this inbound item is one this proxy mislabelled, by all three of §6.5.1's conditions.

    All three, because each one alone is wrong. Without the type check it would reach items that never carried a seal; without the seal check it would strip ids from reasoning items upstream is perfectly willing to look up; without the id check it would strip an id upstream issued, which is the working case.
    """
    if not isinstance(item, dict):
        return False
    entry = cast(dict[str, Any], item)
    if entry.get("type") != "reasoning":
        return False
    if not entry.get("encrypted_content"):
        return False
    item_id = entry.get("id")
    return isinstance(item_id, str) and _MINTED_REASONING_ID.fullmatch(item_id) is not None


async def repair_minted_reasoning_ids(context: RequestContext, *, enabled: bool) -> None:
    """Drop the `id` from every inbound reasoning item matching the shape this proxy used to mint.

    **Three gates, and all three are the Spec's product domain rather than defensive coding** (§6.5.3): the switch, a request that arrived as Responses, and a leg that is not translating. The first version of this checked only `target_format` and justified the omission by claiming a translated body has no Responses `input` array to walk. That claim is false — `to_openai_responses()` always builds one, and `_reasoning_item()` can put a sealed reasoning item in it — and it was false in a way that would have gone unnoticed, because today's translator writes no id onto that item, so the pass finds nothing and looks correct. A domain implemented by a coincidence is a domain that moves the first time the coincidence does.

    Every other field is left exactly as it arrived, the seal included, and an item that fails any of the three item conditions is not touched at all. An unrecognised id is upstream's to resolve or reject; guessing on its behalf is how a repair becomes a second defect.
    """
    if not enabled:
        return
    if context.inbound_format is not WireFormat.OPENAI_RESPONSES:
        return
    if context.translation_required:
        return
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return
    items = context.payload.get("input")
    if not isinstance(items, list):
        return

    repaired = 0
    for item in cast(list[Any], items):
        if not _is_minted_sealed_reasoning(item):
            continue
        del cast(dict[str, Any], item)["id"]
        repaired += 1

    if repaired:
        # Never silent. The rewrite this repairs was itself unrecorded, and that is most of why issue #4 took a full investigation to attribute rather than a log line to read.
        logger.info(
            "removed %d reasoning item id(s) this proxy had minted; upstream cannot verify a seal against them",
            repaired,
        )
