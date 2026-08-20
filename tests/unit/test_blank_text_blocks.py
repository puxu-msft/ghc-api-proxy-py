"""What happens to a text block that carries no text by the time upstream sees it.

Upstream rejects the whole request over one of these: `400 messages: text content blocks must be non-empty`, and a sibling wording, `text content blocks must contain non-whitespace text`, for a block that is only spaces. Production hit the first on 2026-08-20 twice in a row on `/v1/messages` with `claude-opus-5`, and the same rejection is in this machine's transcripts from 2026-07-15 against the previous service, so it is a standing property of the leg rather than something the rewrite introduced.

The rule itself is not new here. `app.anthropic.sanitize.text_blocks.filter_empty_text_blocks` has applied it since the existing chain was written, with the same `.strip()` predicate the reference implementation uses; the new chain never called it, and `tests/unit/test_module_boundaries.py` pins that the new chain does not reach the module it lives in. These tests cover the copy that the new chain does call.
"""

from typing import Any

import pytest

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.config.schema import FixAnthropicRequestHook
from app.pipeline.anthropic_request_hook import fix_anthropic_request


def _fix(payload: dict[str, Any], *, upstream_is_anthropic: bool = True) -> None:
    fix_anthropic_request(
        payload, FixAnthropicRequestHook(), upstream_is_anthropic=upstream_is_anthropic
    )


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
    """Emptying `content` trades one rejection for another, so the request goes out as it arrived.

    The reference implementation has this exact hole — it filters without a surviving-block check and sends `content: []` — which is why it is pinned here rather than left to reading.
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


def test_the_responses_leg_is_left_alone() -> None:
    """The primary path keeps the bytes it had.

    Only the Anthropic upstream is known to refuse a blank block. On the Responses leg it is still carried into the joined `instructions` string and into the text parts, so dropping it here would change the primary path's output over a rule that was never measured against it.
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

    _fix(payload, upstream_is_anthropic=False)

    assert payload["system"] == [
        {"type": "text", "text": "be brief"},
        {"type": "text", "text": ""},
    ]
    assert _content(payload) == [
        {"type": "text", "text": ""},
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
    ]
