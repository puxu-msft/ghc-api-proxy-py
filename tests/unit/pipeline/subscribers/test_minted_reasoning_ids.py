"""`builtin:repair-minted-reasoning-ids` — GitHub issue #4's request-side repair.

`.dev/docs/direct-passthrough/spec.md` §6.5 is the clause. What is asserted here is the predicate's three item conditions, the three gates, and the switch, because every one of them is a way this pass can do harm rather than merely fail to help: it edits a body on the way to upstream, and the item it edits is one upstream would otherwise have accepted whenever the predicate is wrong.

**The configuration default is not asserted here** and cannot be: these call the function directly with an `enabled` argument, which is downstream of the schema, the composition and the registry. `tests/int/test_pipeline_app.py` holds that pair.
"""

import copy
from typing import Any

import pytest

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.minted_reasoning_ids import repair_minted_reasoning_ids

# `f"rs_{uuid4}_{output_index}"`, the shape the known production path emits. This exact string is the id upstream named when the issue #4 body was replayed on 2026-09-01.
MINTED = "rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0"


def sealed(item_id: str | None = MINTED, *, seal: str | None = "sealed") -> dict[str, Any]:
    item: dict[str, Any] = {"type": "reasoning", "summary": []}
    if item_id is not None:
        item["id"] = item_id
    if seal is not None:
        item["encrypted_content"] = seal
    return item


def context_with(items: list[Any]) -> RequestContext:
    return context_for({"model": "gpt-model", "input": items})


def context_for(payload: dict[str, Any]) -> RequestContext:
    """A context on the one leg this pass serves: Responses in, Responses out, nothing translated."""
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="gpt-model",
        payload=payload,
    )
    context.target_format = WireFormat.OPENAI_RESPONSES
    context.translation_required = False
    return context


async def test_a_minted_id_on_a_sealed_item_is_removed_and_nothing_else_is() -> None:
    """The repair itself: the label goes, the seal and every other field stay.

    Dropping `encrypted_content` instead would also satisfy upstream — measured — and would throw the turn's reasoning away. Asserted as an equality against the whole item rather than as `"id" not in item`, so a pass that also edited the seal, the summary or the type would fail here rather than somewhere downstream.
    """
    context = context_with([sealed()])

    await repair_minted_reasoning_ids(context, enabled=True)

    assert context.payload["input"] == [
        {"type": "reasoning", "summary": [], "encrypted_content": "sealed"}
    ]


@pytest.mark.parametrize(
    ("item", "why"),
    [
        (sealed(item_id="rs_abc123"), "an id that is not this proxy's shape at all"),
        (
            sealed(item_id="rs_not-a-uuid-at-all_0"),
            "the loose `rs_ + anything + _digits` shape the user's ruling excluded",
        ),
        (
            sealed(item_id="rs_00000000-0000-1000-8000-000000000000_0"),
            "a version-1 UUID: well formed, and not something `uuid4()` can produce",
        ),
        (
            sealed(item_id="rs_136b08ff-f6b2-4b41-c938-ae6d74eb7496_0"),
            "an RFC variant nibble `uuid4()` never writes — the fourth group starts `c`, not one of `89ab`",
        ),
        (
            sealed(item_id="rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_00"),
            "a leading zero on the index, which `str()` of an `int` does not write",
        ),
        (
            sealed(item_id="rs_136B08FF-F6B2-4B41-8F38-AE6D74EB7496_0"),
            "upper-case hex, which `uuid4()` does not produce",
        ),
        (
            sealed(item_id=f"prefix_{MINTED}"),
            "the minted shape as a suffix of a longer id",
        ),
        (
            sealed(item_id="rs_resp_202608310314088f84634097214507_1", seal=None),
            "a second minting shape that really occurs — `copilot-api-js` on this same port produced it — but which carries plaintext rather than a seal, so upstream has no binding to fail and it must be left alone",
        ),
        (sealed(seal=None), "no seal, so upstream has no binding to verify"),
        (sealed(seal=""), "an empty seal, which is not a seal"),
        ({"type": "message", "id": MINTED, "encrypted_content": "sealed"}, "not a reasoning item"),
        ("not-a-dict", "not an object at all"),
    ],
)
async def test_ids_outside_this_proxy_s_own_spelling_are_left_exactly_as_they_arrived(
    item: Any, why: str
) -> None:
    """The controls, and they are the point of the whole exercise.

    A repair that fires too widely is worse than no repair: `rs_` is also how OpenAI spells a reasoning item, so a loose pattern risks stripping an id some upstream legitimately issued and breaking a conversation that was working. The user ruled the narrow shape for that reason.

    The cases are the ways a pattern can be wider than `_item_id`'s output, not a claim to have enumerated every possible id. Three of them — version, variant, leading zero — come from an independent review that constructed them against an earlier pattern and watched it strip them.
    """
    context = context_with([copy.deepcopy(item)])

    await repair_minted_reasoning_ids(context, enabled=True)

    assert context.payload["input"] == [item], why


async def test_it_does_nothing_at_all_unless_it_is_switched_on() -> None:
    """Off is the ruling and `spec.md` §2.7's requirement.

    This pins the function's own behaviour on `enabled=False`; that the shipped configuration actually leaves it false is a different claim, asserted end to end in `tests/int/test_pipeline_app.py`.
    """
    context = context_with([sealed()])

    await repair_minted_reasoning_ids(context, enabled=False)

    assert context.payload["input"] == [sealed()]


@pytest.mark.parametrize(
    ("field", "value", "why"),
    [
        (
            "target_format",
            WireFormat.ANTHROPIC_MESSAGES,
            "a body going somewhere that does not verify these bindings",
        ),
        (
            "inbound_format",
            WireFormat.ANTHROPIC_MESSAGES,
            "a request that did not arrive as Responses, so this proxy never handed its client a Responses item id",
        ),
        (
            "translation_required",
            True,
            "a translating leg, which `spec.md` §6.5.3 puts outside this pass's domain",
        ),
    ],
)
async def test_each_of_the_three_gates_keeps_the_body_out_of_reach(
    field: str, value: object, why: str
) -> None:
    """The domain gates, one case each, because a missing one is invisible until it is not.

    The translating case is the one that matters and the one the first implementation lacked: `to_openai_responses()` always builds an `input` array and can put a sealed reasoning item in it, so the leg this pass does not serve does have bodies it could walk. Today's translator writes no id onto that item, which is exactly why the missing gate looked harmless — the pass would have found nothing and reported success.
    """
    context = context_with([sealed()])
    setattr(context, field, value)

    await repair_minted_reasoning_ids(context, enabled=True)

    assert context.payload["input"] == [sealed()], why


async def test_it_repairs_every_such_item_not_just_the_first() -> None:
    """A poisoned history carries one per assistant turn — the issue #4 body held fifteen — and one 400 needs only one survivor."""
    context = context_with(
        [
            sealed(item_id="rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0"),
            {"type": "message", "role": "user", "content": []},
            sealed(item_id="rs_9fe1ad05-1120-4f52-bd32-33a78fa1cbb5_7"),
        ]
    )

    await repair_minted_reasoning_ids(context, enabled=True)

    forwarded: list[Any] = context.payload["input"]
    assert len(forwarded) == 3
    assert all("id" not in item for item in forwarded if isinstance(item, dict))


async def test_it_says_how_many_it_repaired(caplog: pytest.LogCaptureFixture) -> None:
    """A silent body rewrite is the shape of the defect being repaired.

    The rewrite that caused issue #4 left no record, which is most of why attributing it took a full investigation rather than reading a log line. `spec.md` §6.5.4 makes the count part of the contract.
    """
    context = context_with([sealed(), sealed(item_id="rs_9fe1ad05-1120-4f52-bd32-33a78fa1cbb5_7")])

    with caplog.at_level("INFO"):
        await repair_minted_reasoning_ids(context, enabled=True)

    assert "removed 2 reasoning item id(s)" in caplog.text


async def test_a_responses_body_with_no_input_array_is_not_a_crash() -> None:
    """A malformed or minimal direct Responses body still reaches this pass, and this pass is not the thing that should refuse it."""
    context = context_for({"model": "gpt-model"})

    await repair_minted_reasoning_ids(context, enabled=True)

    assert context.payload == {"model": "gpt-model"}
