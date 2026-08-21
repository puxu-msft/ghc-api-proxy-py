"""Removing the attribution line Claude Code prepends to the system prompt.

The line is `x-anthropic-billing-header: cc_version=…; cc_entrypoint=…;` and it is addressed to Anthropic's billing rather than to any model. Upstream accepts it — measured 2026-08-21 across fifteen shapes, all 200 — so what these assert is not a compatibility repair. What they protect is the discrimination: the pattern has to catch a header line pasted into a prompt and has to leave prose alone, and the second half is where a careless pattern eats the first sentence of somebody's system prompt.
"""

from typing import Any

from app.pipeline.anthropic_request_hook import strip_attribution_lines

ATTRIBUTION = "x-anthropic-billing-header: cc_version=1.0; cc_entrypoint=cli;"
SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."


def test_the_attribution_line_goes_and_the_prompt_stays() -> None:
    payload: dict[str, Any] = {
        "system": [{"type": "text", "text": f"{ATTRIBUTION}\n{SYSTEM}"}],
    }

    assert strip_attribution_lines(payload) == 1
    assert payload["system"] == [{"type": "text", "text": SYSTEM}]


def test_block_metadata_survives_the_edit() -> None:
    """`cache_control` is the reason this rebuilds the block instead of replacing it.

    Claude Code marks the first system block as a cache breakpoint. Dropping that while removing a line from the same block would silently move where the prompt cache begins, which costs money on every subsequent request and shows up nowhere.
    """
    payload: dict[str, Any] = {
        "system": [
            {
                "type": "text",
                "text": f"{ATTRIBUTION}\n{SYSTEM}",
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }

    assert strip_attribution_lines(payload) == 1
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert payload["system"][0]["text"] == SYSTEM


def test_a_block_that_was_only_attribution_is_dropped() -> None:
    payload: dict[str, Any] = {
        "system": [{"type": "text", "text": ATTRIBUTION}, {"type": "text", "text": SYSTEM}],
    }

    assert strip_attribution_lines(payload) == 1
    assert payload["system"] == [{"type": "text", "text": SYSTEM}]


def test_a_system_that_was_only_attribution_is_removed_entirely() -> None:
    """An empty `system` is not sent as `""`. A blank system block is one of the shapes the Anthropic leg rejects, so leaving one behind would turn a tidy-up into a 400."""
    payload: dict[str, Any] = {"system": [{"type": "text", "text": ATTRIBUTION}]}

    assert strip_attribution_lines(payload) == 1
    assert "system" not in payload


def test_a_plain_string_system_is_handled_too() -> None:
    """Claude Code sends both spellings and the array one is not guaranteed."""
    payload: dict[str, Any] = {"system": f"{ATTRIBUTION}\n{SYSTEM}"}

    assert strip_attribution_lines(payload) == 1
    assert payload["system"] == SYSTEM


def test_several_stacked_lines_all_go() -> None:
    payload: dict[str, Any] = {
        "system": [{"type": "text", "text": f"{ATTRIBUTION}\nx-other-header: a=b;\n{SYSTEM}"}],
    }

    assert strip_attribution_lines(payload) == 2
    assert payload["system"] == [{"type": "text", "text": SYSTEM}]


def test_prose_that_opens_with_a_colon_is_left_alone() -> None:
    """The discrimination this whole pattern exists for.

    Every one of these opens a real system prompt with a colon and none of them is a header. A pattern matching `\\S+:` would delete the first line of all four — silently, and only for the users who write that way.
    """
    for opener in ("Note: be brief.", "Important: never guess.", "Step 1: read the file.", "Warning: this is beta."):
        payload: dict[str, Any] = {"system": [{"type": "text", "text": f"{opener}\n{SYSTEM}"}]}

        assert strip_attribution_lines(payload) == 0, opener
        assert payload["system"][0]["text"] == f"{opener}\n{SYSTEM}", opener


def test_a_hyphenated_word_inside_a_sentence_is_not_a_header() -> None:
    """`fullmatch` against the whole line rather than a search, so a sentence that happens to contain both a hyphen and a colon is safe."""
    text = "This is a well-known problem: read the docs.\n" + SYSTEM
    payload: dict[str, Any] = {"system": [{"type": "text", "text": text}]}

    assert strip_attribution_lines(payload) == 0
    assert payload["system"][0]["text"] == text


def test_an_attribution_line_in_the_middle_of_a_prompt_stays() -> None:
    """Only a prefix is stripped. A header-shaped line further down was written by whoever wrote the prompt — quoting one is a normal thing for a prompt about HTTP to do."""
    text = f"{SYSTEM}\n{ATTRIBUTION}"
    payload: dict[str, Any] = {"system": [{"type": "text", "text": text}]}

    assert strip_attribution_lines(payload) == 0
    assert payload["system"][0]["text"] == text


def test_the_body_the_caller_parsed_is_not_mutated() -> None:
    """`message-format-sanitize.md` requires the record of the original client request to be unaffected by this. The payload is a shallow copy of the parsed body, so editing a block in place would reach back into it."""
    original_block = {"type": "text", "text": f"{ATTRIBUTION}\n{SYSTEM}"}
    original_system = [original_block]
    payload: dict[str, Any] = {"system": original_system}

    strip_attribution_lines(payload)

    assert original_block["text"] == f"{ATTRIBUTION}\n{SYSTEM}"
    assert original_system == [original_block]


def test_a_body_with_no_system_is_untouched() -> None:
    payload: dict[str, Any] = {"messages": []}

    assert strip_attribution_lines(payload) == 0
    assert payload == {"messages": []}
