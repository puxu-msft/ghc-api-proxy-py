"""What happens to a text block that carries no text, on the leg that refuses one.

Upstream rejects the whole request over one of these: `400 messages: text content blocks must be non-empty`, and a sibling wording, `text content blocks must contain non-whitespace text`, for a block that is only spaces. Production hit the first on 2026-08-20 twice in a row on `/v1/messages` with `claude-opus-5`, and the same rejection is in this machine's transcripts from 2026-07-15 against the previous service, so it is a standing property of the leg rather than something the rewrite introduced.

Which leg is not a guess. `exp/260820-empty-text-probe/` asked the live upstream: `/responses` answers 200 to an empty `input_text`, to a whitespace-only one, and to an assistant turn carrying an empty `output_text`, while `/v1/messages` answers 400 in the same run with the same credentials. So this runs at `attempt.prepare`, where the routed endpoint is known, and does nothing at all to a body bound for Responses.
"""

from typing import Any

import pytest

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.blank_text import drop_blank_text_blocks


def _context(payload: dict[str, Any], *, target: WireFormat = WireFormat.ANTHROPIC_MESSAGES) -> RequestContext:
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload=payload,
    )
    context.target_format = target
    return context


async def _run(payload: dict[str, Any], *, target: WireFormat = WireFormat.ANTHROPIC_MESSAGES) -> dict[str, Any]:
    context = _context(payload, target=target)
    await drop_blank_text_blocks(context)
    return context.payload


def _content(payload: dict[str, Any], index: int = 0) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = payload["messages"]
    return messages[index]["content"]


_THINKING_A: dict[str, Any] = {"type": "thinking", "thinking": "first", "signature": "sig-a"}
_THINKING_B: dict[str, Any] = {"type": "thinking", "thinking": "second", "signature": "sig-b"}
_BLANK: dict[str, Any] = {"type": "text", "text": ""}


async def test_a_blank_text_block_beside_real_content_is_dropped() -> None:
    """The shape that costs a whole request for a block that says nothing.

    This is the production one: the synthesised placeholder landed first and the real tool call twelve seconds later, so the turn the client stored and replayed was exactly this.
    """
    payload = await _run(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
                    ],
                }
            ]
        }
    )

    assert _content(payload) == [
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
    ]


async def test_whitespace_only_text_counts_as_blank() -> None:
    """Upstream refuses these under their own error message, so `== ""` would have missed half the rule."""
    payload = await _run(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "   \n\t "},
                        {"type": "text", "text": "what changed?"},
                    ],
                }
            ]
        }
    )

    assert _content(payload) == [{"type": "text", "text": "what changed?"}]


async def test_a_message_of_nothing_but_blank_text_is_left_alone() -> None:
    """The one place the rule stops, and why it stops there rather than everywhere.

    A turn is not a field that can be dropped for saying nothing: the rest of the history is paired against it by position, and a `tool_result` names a `tool_use` in the turn before. `content: []` is refused as surely as the blank block was, so emptying it would trade one rejection for another while also inventing a body the client never sent. It goes out as it arrived and upstream names what is actually wrong with it.

    The reference implementation has this exact hole — it filters without a surviving-block check and sends `content: []` — which is why this is pinned rather than left to reading.
    """
    payload = await _run({"messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}]})

    assert _content(payload) == [{"type": "text", "text": ""}]


async def test_a_blank_block_between_two_thinking_blocks_becomes_a_real_separator() -> None:
    """Removing it outright would leave behind the arrangement the layout pass exists to prevent.

    That pass ran before translation, long before this one, so it cannot clean up after this. The blank block was serving as a separator by accident; it is replaced by one upstream accepts rather than simply deleted.
    """
    payload = await _run(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "first", "signature": "sig-a"},
                        {"type": "text", "text": ""},
                        {"type": "thinking", "thinking": "second", "signature": "sig-b"},
                    ],
                }
            ]
        }
    )

    assert _content(payload) == [
        {"type": "thinking", "thinking": "first", "signature": "sig-a"},
        {"type": "text", "text": SYNTHETIC_SEPARATOR},
        {"type": "thinking", "thinking": "second", "signature": "sig-b"},
    ]


async def test_the_system_prompt_is_held_to_the_same_rule() -> None:
    """`system` carries the same blocks and is refused on the same grounds."""
    payload = await _run(
        {
            "system": [
                {"type": "text", "text": "You are a proxy."},
                {"type": "text", "text": ""},
            ],
            "messages": [],
        }
    )

    assert payload["system"] == [{"type": "text", "text": "You are a proxy."}]


async def test_a_system_prompt_of_nothing_loses_the_field_rather_than_emptying_it() -> None:
    """Saying nothing and having nothing to say are the same thing here, and only one is a body upstream takes.

    `system: []` is refused as surely as the blank block was, so emptying the list would trade one rejection for another. Dropping the field is the spelling that means the same and is accepted — which is exactly why a turn cannot be treated this way.
    """
    payload = await _run(
        {
            "system": [{"type": "text", "text": ""}, {"type": "text", "text": "  \n"}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        }
    )

    assert "system" not in payload
    assert _content(payload) == [{"type": "text", "text": "hi"}]


async def test_a_body_with_nothing_blank_is_unchanged() -> None:
    """The common case must not be rewritten, including the string form of `system`."""
    payload = await _run(
        {
            "system": "You are a proxy.",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }
    )

    assert payload == {
        "system": "You are a proxy.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    }


async def test_a_body_bound_for_responses_is_not_touched() -> None:
    """Measured, not assumed: that endpoint takes the shape, so rewriting it would be a change with nothing behind it.

    `exp/260820-empty-text-probe/` sent an empty `input_text`, a whitespace-only one, and an empty `output_text` on an assistant turn to the live `/responses`; all three came back 200, in the run whose positive control got 400 from `/v1/messages` over the block below.
    """
    original: dict[str, Any] = {
        "system": [{"type": "text", "text": "be brief"}, {"type": "text", "text": ""}],
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
                ],
            }
        ],
    }

    payload = await _run(
        {
            "system": [{"type": "text", "text": "be brief"}, {"type": "text", "text": ""}],
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
                    ],
                }
            ],
        },
        target=WireFormat.OPENAI_RESPONSES,
    )

    assert payload == original


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            [_THINKING_A, _BLANK, _BLANK, _THINKING_B],
            [_THINKING_A, {"type": "text", "text": SYNTHETIC_SEPARATOR}, _THINKING_B],
        ),
        ([_BLANK, _THINKING_A], [_THINKING_A]),
        ([_THINKING_A, _BLANK], [_THINKING_A]),
        ([_BLANK, _THINKING_A, _BLANK, _THINKING_B, _BLANK], None),
    ],
    ids=["run-of-two", "leading", "trailing", "leading-middle-trailing"],
)
async def test_the_separator_is_spent_only_where_one_is_needed(
    content: list[dict[str, Any]], expected: list[dict[str, Any]] | None
) -> None:
    """One separator where two thinking blocks would otherwise meet, and none anywhere else.

    A run of blanks must not turn into a run of separators, and a blank at either end has nothing to separate — it is simply gone. These are the shapes the lookahead exists for; without them a version that emitted one separator per blank, or one for a trailing blank, would still pass every test above.
    """
    payload = await _run({"messages": [{"role": "assistant", "content": content}]})

    if expected is None:
        expected = [
            _THINKING_A,
            {"type": "text", "text": SYNTHETIC_SEPARATOR},
            _THINKING_B,
        ]
    assert _content(payload) == expected


@pytest.mark.parametrize(
    ("block", "dropped"),
    [
        ({"type": "text"}, True),
        ({"type": "text", "text": None}, True),
        ({"type": "text", "text": 0}, False),
        ({"type": "text", "text": []}, False),
        ({"type": "text", "text": {}}, False),
    ],
    ids=["missing", "null", "zero", "list", "dict"],
)
async def test_where_the_predicate_draws_its_line(block: dict[str, Any], dropped: bool) -> None:
    """A `text` that is absent or null carries nothing and goes; one of the wrong type stays.

    The split is deliberate and is the part a reader is most likely to get backwards. Dropping a malformed block would turn a client bug into a silent rewrite, and upstream naming the field is more use to whoever has to fix it than a block that quietly disappeared.
    """
    payload = await _run(
        {"messages": [{"role": "user", "content": [block, {"type": "text", "text": "anchor"}]}]}
    )

    survivors = _content(payload)
    assert (block not in survivors) is dropped
    assert {"type": "text", "text": "anchor"} in survivors
