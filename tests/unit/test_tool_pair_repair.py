"""Calls nothing answered, and answers nothing called.

Both endpoints refuse a broken `tool_use` / `tool_result` pair, and each says so in its own words. Measured 2026-08-20 against the live upstream, `exp/260820-tool-pair-probe/`:

| probe | shape | result |
|---|---|---|
| G0 | well-paired | 200 |
| G1 | a call the next turn does not answer | 400 ``messages.2: `tool_use` ids were found without `tool_result` blocks immediately after`` |
| G2 | a result naming no call before it | 400 ``unexpected `tool_use_id` found in `tool_result` blocks`` |
| G3 | the same id used twice | **200** |
| G4 | two assistant turns in a row | **200** |
| G5 | the translated equivalent on `/responses` | 400 `No tool output found for function call call_1.` |

G5 is why the repair runs before translation: the invariant belongs to neither leg in particular, so repairing it on the outbound Anthropic leg alone would leave the primary path broken the same way. G3 is why ids are not deduplicated — the existing chain removes a reused id, and this upstream accepts one. G4 is what makes dropping an emptied turn an available repair rather than a guess.

How a body gets into this state: history edited between turns. A compaction that keeps the call and drops the answer, a `context_management` edit, an interrupted turn where the call was recorded and the result never was.
"""

from typing import Any

from app.config.schema import FixAnthropicRequestHook
from app.pipeline.anthropic_request_hook import fix_anthropic_request, repair_tool_pairs

ASK: dict[str, Any] = {"role": "user", "content": [{"type": "text", "text": "weather?"}]}


def call(use_id: str = "toolu_1", *, with_text: bool = False) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "tool_use", "id": use_id, "name": "get_weather", "input": {}}]
    if with_text:
        content.insert(0, {"type": "text", "text": "checking"})
    return {"role": "assistant", "content": content}


def answer(use_id: str = "toolu_1", *, with_text: bool = False) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "tool_result", "tool_use_id": use_id, "content": "18C"}]
    if with_text:
        content.append({"type": "text", "text": "thanks"})
    return {"role": "user", "content": content}


def kinds(message: dict[str, Any]) -> list[str]:
    return [block["type"] for block in message["content"]]


def test_a_well_paired_conversation_is_untouched() -> None:
    """The common case. A repair that fires here would be removing what upstream accepts."""
    messages: list[Any] = [ASK, call(), answer()]

    assert repair_tool_pairs(messages) == (0, 0, 0)
    assert kinds(messages[1]) == ["tool_use"]
    assert kinds(messages[2]) == ["tool_result"]


def test_a_call_the_next_turn_never_answers_is_removed() -> None:
    """G1: upstream refuses the whole body over it, naming the turn and the id."""
    messages: list[Any] = [ASK, call(with_text=True), {"role": "user", "content": [{"type": "text", "text": "never mind"}]}]

    assert repair_tool_pairs(messages) == (1, 0, 0)
    assert kinds(messages[1]) == ["text"], "the rest of the turn must survive"


def test_an_answer_to_a_call_that_is_not_there_is_removed() -> None:
    """G2: the mirror image, and upstream refuses it in different words."""
    messages: list[Any] = [ASK, {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}, answer(with_text=True)]

    assert repair_tool_pairs(messages) == (0, 1, 0)
    assert kinds(messages[2]) == ["text"]


def test_a_result_that_arrives_a_turn_late_is_an_orphan_on_both_counts() -> None:
    """`immediately after` is upstream's own wording, so the pairing looks exactly one turn ahead.

    The call loses its answer and the answer loses its call — both are removed, which is what upstream would have refused the body for.
    """
    messages: list[Any] = [
        ASK,
        call(with_text=True),
        {"role": "user", "content": [{"type": "text", "text": "wait"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        answer(with_text=True),
    ]

    assert repair_tool_pairs(messages) == (1, 1, 0)


def test_only_the_unanswered_call_goes_when_a_turn_makes_several() -> None:
    messages: list[Any] = [
        ASK,
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "a", "input": {}},
                {"type": "tool_use", "id": "toolu_2", "name": "b", "input": {}},
            ],
        },
        answer("toolu_2"),
    ]

    assert repair_tool_pairs(messages) == (1, 0, 0)
    assert [block["id"] for block in messages[1]["content"]] == ["toolu_2"]


def test_a_reused_id_is_left_alone() -> None:
    """G3: this upstream answers 200 to a conversation that reuses one.

    The existing chain removes it. Removing something upstream accepts, on the strength of a rule it does not enforce, takes a tool call away from the model for nothing.
    """
    messages: list[Any] = [ASK, call(), answer(), call(), answer()]

    assert repair_tool_pairs(messages) == (0, 0, 0)


def test_a_turn_left_with_nothing_is_dropped_rather_than_emptied() -> None:
    """G4 is what makes this available: two same-role turns in a row are accepted.

    `content: []` would not be — upstream refuses that for a user turn in its own words. Before G4 was measured neither rewrite was known to work and the orphan had to travel; now one of them is.
    """
    messages: list[Any] = [ASK, call(), answer(), {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "gone", "content": "x"}]}]

    assert repair_tool_pairs(messages) == (0, 1, 1)
    assert len(messages) == 3
    assert kinds(messages[2]) == ["tool_result"]


def test_a_body_is_never_left_with_no_turns_at_all() -> None:
    """A request with no messages is a different request, not a repaired one, so the orphan travels."""
    messages: list[Any] = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "gone", "content": "x"}]}]

    assert repair_tool_pairs(messages) == (0, 1, 0)
    assert len(messages) == 1


def test_a_turn_that_arrived_empty_is_not_this_chain_s_to_remove() -> None:
    """Only a turn this repair emptied is dropped.

    `content: []` from the client is the client's own body, and upstream naming it is the answer the client needs. Telling the two apart is why the drop happens inside the repair, where what was removed is still known, rather than in a later pass that can only see the result — an earlier revision did the latter and removed this one too.
    """
    messages: list[Any] = [ASK, {"role": "user", "content": []}, {"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    assert repair_tool_pairs(messages) == (0, 0, 0)
    assert len(messages) == 3
    assert messages[1]["content"] == []


def test_the_repair_runs_from_the_hook() -> None:
    """Registration proves nothing; this proves the body that leaves the hook is the repaired one."""
    body: dict[str, Any] = {"messages": [ASK, call(with_text=True), {"role": "user", "content": [{"type": "text", "text": "no"}]}]}

    fix_anthropic_request(body, FixAnthropicRequestHook())

    assert kinds(body["messages"][1]) == ["text"]
