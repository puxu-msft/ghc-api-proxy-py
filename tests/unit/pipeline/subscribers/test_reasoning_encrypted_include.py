"""`builtin:reasoning-encrypted-include` — the configured shape of the encrypted-reasoning ask.

What is asserted here is the policy's three values against the `include` shapes a request can actually arrive with, and the target-format gate, because the pass edits a body on the way to upstream and every wrong predicate is an edit upstream never asked for.

**The configuration default is not asserted here** and cannot be: these call the function directly with a `policy` argument, which is downstream of the schema, the composition and the registry. `tests/unit/pipeline/subscribers/test_builtin_subscribers.py` holds the registered set; the schema holds the default.
"""

from typing import Any

import pytest

from app.config.schema import ReasoningEncryptedIncludePolicy
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.reasoning_encrypted_include import (
    REASONING_ENCRYPTED_CONTENT,
    shape_reasoning_encrypted_include,
)

OTHER_INCLUDABLE = "file_search_call.results"


def context_for(
    payload: dict[str, Any],
    *,
    target: WireFormat = WireFormat.OPENAI_RESPONSES,
) -> RequestContext:
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="gpt-model",
        payload=payload,
    )
    context.target_format = target
    context.translation_required = False
    return context


async def test_passthrough_never_touches_the_body() -> None:
    """The default policy: absent stays absent, present stays present, and an include the pass cannot parse is nobody here's business."""
    payloads = [
        {"model": "m"},
        {"model": "m", "include": [OTHER_INCLUDABLE]},
        {"model": "m", "include": [REASONING_ENCRYPTED_CONTENT]},
        {"model": "m", "include": "reasoning.encrypted_content"},
    ]
    for payload in payloads:
        context = context_for(dict(payload))

        await shape_reasoning_encrypted_include(context, policy="passthrough")

        assert context.payload == payload


async def test_always_add_creates_include_when_absent() -> None:
    context = context_for({"model": "m"})

    await shape_reasoning_encrypted_include(context, policy="always_add")

    assert context.payload["include"] == [REASONING_ENCRYPTED_CONTENT]


async def test_always_add_appends_to_an_existing_list_without_disturbing_it() -> None:
    context = context_for({"model": "m", "include": [OTHER_INCLUDABLE]})

    await shape_reasoning_encrypted_include(context, policy="always_add")

    assert context.payload["include"] == [OTHER_INCLUDABLE, REASONING_ENCRYPTED_CONTENT]


async def test_always_add_is_idempotent() -> None:
    context = context_for({"model": "m", "include": [REASONING_ENCRYPTED_CONTENT]})

    await shape_reasoning_encrypted_include(context, policy="always_add")
    await shape_reasoning_encrypted_include(context, policy="always_add")

    assert context.payload["include"] == [REASONING_ENCRYPTED_CONTENT]


async def test_always_add_leaves_an_unrecognised_include_shape_alone() -> None:
    """A non-list `include` is upstream's to accept or refuse; reshaping it here would invent a contract."""
    context = context_for({"model": "m", "include": "reasoning.encrypted_content"})

    await shape_reasoning_encrypted_include(context, policy="always_add")

    assert context.payload["include"] == "reasoning.encrypted_content"


async def test_always_strip_removes_the_entry_and_keeps_the_rest() -> None:
    context = context_for(
        {"model": "m", "include": [OTHER_INCLUDABLE, REASONING_ENCRYPTED_CONTENT]}
    )

    await shape_reasoning_encrypted_include(context, policy="always_strip")

    assert context.payload["include"] == [OTHER_INCLUDABLE]


async def test_always_strip_drops_an_include_left_empty_by_the_removal() -> None:
    """After the strip an empty array says nothing at all, so the key goes with it."""
    context = context_for({"model": "m", "include": [REASONING_ENCRYPTED_CONTENT]})

    await shape_reasoning_encrypted_include(context, policy="always_strip")

    assert "include" not in context.payload


async def test_always_strip_is_a_no_op_without_the_entry() -> None:
    for payload in ({"model": "m"}, {"model": "m", "include": [OTHER_INCLUDABLE]}):
        context = context_for(dict(payload))

        await shape_reasoning_encrypted_include(context, policy="always_strip")

        assert context.payload == payload


@pytest.mark.parametrize("policy", ["always_add", "always_strip"])
async def test_non_responses_targets_are_never_touched(
    policy: ReasoningEncryptedIncludePolicy,
) -> None:
    """An Anthropic Messages upstream has no `include` parameter; neither has a Chat Completions leg."""
    payload = {"model": "m", "include": [REASONING_ENCRYPTED_CONTENT]}
    context = context_for(dict(payload), target=WireFormat.ANTHROPIC_MESSAGES)

    await shape_reasoning_encrypted_include(context, policy=policy)

    assert context.payload == payload
