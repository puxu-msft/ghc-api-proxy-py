"""What happens to a text block that carries no text by the time upstream sees it.

Upstream rejects the whole request over one of these: `400 messages: text content blocks must be non-empty`, and a sibling wording, `text content blocks must contain non-whitespace text`, for a block that is only spaces. Production hit the first on 2026-08-20 twice in a row on `/v1/messages` with `claude-opus-5`, and the same rejection is in this machine's transcripts from 2026-07-15 against the previous service, so it is a standing property of the leg rather than something the rewrite introduced.

The rule itself is not new here. `app.anthropic.sanitize.text_blocks.filter_empty_text_blocks` has applied it since the existing chain was written, with the same `.strip()` predicate the reference implementation uses; the new chain never called it, and `tests/unit/test_module_boundaries.py` pins that the new chain does not reach the module it lives in. These tests cover the copy that the new chain does call.
"""

from typing import Any

import pytest

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.config.schema import FixAnthropicRequestHook
from app.pipeline.anthropic_request_hook import fix_anthropic_request


def _fix(payload: dict[str, Any]) -> None:
    fix_anthropic_request(payload, FixAnthropicRequestHook())


def _content(payload: dict[str, Any], index: int = 0) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = payload["messages"]
    return messages[index]["content"]


def test_a_blank_text_block_beside_real_content_is_dropped() -> None:
    """The shape that costs a whole request for a block that says nothing."""
    payload: dict[str, Any] = {
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

    _fix(payload)

    assert _content(payload) == [
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
    ]


def test_whitespace_only_text_counts_as_blank() -> None:
    """Upstream refuses these under their own error message, so `== ""` would have missed half the rule."""
    payload: dict[str, Any] = {
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

    _fix(payload)

    assert _content(payload) == [{"type": "text", "text": "what changed?"}]


def test_a_message_of_nothing_but_blank_text_is_left_alone() -> None:
    """The one place the rule stops, and why it stops there rather than everywhere.

    A turn is not a field that can be dropped for saying nothing: the rest of the history is paired against it by position, and a `tool_result` names a `tool_use` in the turn before. `content: []` is refused as surely as the blank block was, so emptying it would trade one rejection for another while also inventing a body the client never sent. It goes out as it arrived and upstream names what is actually wrong with it.

    The reference implementation has this exact hole — it filters without a surviving-block check and sends `content: []` — which is why this is pinned rather than left to reading.
    """
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}]
    }

    _fix(payload)

    assert _content(payload) == [{"type": "text", "text": ""}]


def test_a_blank_block_stops_hiding_two_adjacent_thinking_blocks() -> None:
    """Why the drop runs before the layout pass rather than after it.

    A blank text block between two thinking blocks makes them look separated, so the layout leaves the pair upstream also rejects. Removing it first lets the layout see the adjacency and spend a real separator on it — one fixup, both rejections.
    """
    payload: dict[str, Any] = {
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

    _fix(payload)

    assert _content(payload) == [
        {"type": "thinking", "thinking": "first", "signature": "sig-a"},
        {"type": "text", "text": SYNTHETIC_SEPARATOR},
        {"type": "thinking", "thinking": "second", "signature": "sig-b"},
    ]


def test_the_system_prompt_is_held_to_the_same_rule() -> None:
    """`system` is refused on the same grounds and is not part of any turn, so the loop would never reach it."""
    payload: dict[str, Any] = {
        "system": [
            {"type": "text", "text": "You are a proxy."},
            {"type": "text", "text": ""},
        ],
        "messages": [],
    }

    _fix(payload)

    assert payload["system"] == [{"type": "text", "text": "You are a proxy."}]


def test_a_body_with_nothing_blank_is_unchanged() -> None:
    """The common case must not be rewritten, including the string form of `system`."""
    payload: dict[str, Any] = {
        "system": "You are a proxy.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    }

    _fix(payload)

    assert payload == {
        "system": "You are a proxy.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    }


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
def test_where_the_predicate_draws_its_line(block: dict[str, Any], dropped: bool) -> None:
    """A `text` that is absent or null carries nothing and goes; one of the wrong type stays.

    The split is deliberate and is the part a reader is most likely to get backwards. Dropping a malformed block would turn a client bug into a silent rewrite, and upstream naming the field is more use to whoever has to fix it than a block that quietly disappeared.
    """
    payload: dict[str, Any] = {
        "messages": [
            {
                "role": "user",
                "content": [block, {"type": "text", "text": "anchor"}],
            }
        ]
    }

    _fix(payload)

    survivors = _content(payload)
    assert (block not in survivors) is dropped
    assert {"type": "text", "text": "anchor"} in survivors


def test_nothing_about_the_route_changes_the_answer() -> None:
    """There is no leg on which a block that says nothing is worth carrying.

    An earlier revision gated this on the outbound upstream, on the grounds that only the Anthropic one is known to refuse a blank block. Ruled against on 2026-08-20: the predicate is that the block carries no meaning, not that some receiver complains about it, so there is nothing left to condition on — this hook no longer takes the route as an argument at all.

    What that means on the wire for the translated leg is a separate question, and one this test cannot answer because it stops at the hook. `tests/http/test_pipeline_app.py` carries that half.
    """
    payload: dict[str, Any] = {
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

    _fix(payload)

    assert payload["system"] == [{"type": "text", "text": "be brief"}]
    assert _content(payload) == [
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
    ]


def test_a_system_prompt_of_nothing_loses_the_field_rather_than_emptying_it() -> None:
    """Saying nothing and having nothing to say are the same thing here, and only one is a body upstream takes.

    `system: []` is refused as surely as the blank block was, so emptying the list would trade one rejection for another. Dropping the field is the spelling that means the same and is accepted — which is exactly why a turn cannot be treated this way; see the test below.
    """
    payload: dict[str, Any] = {
        "system": [{"type": "text", "text": ""}, {"type": "text", "text": "  \n"}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    }

    _fix(payload)

    assert "system" not in payload
    assert _content(payload) == [{"type": "text", "text": "hi"}]
