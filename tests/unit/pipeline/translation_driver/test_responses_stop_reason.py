"""What a non-streaming Responses reply says about why it stopped.

The same rule the streaming assembler follows, held here so the two paths cannot describe one
fact differently: the output-token limit is the only reason with an Anthropic spelling, and it is
the only one translated.
"""

from typing import Any

from app.pipeline.translation_driver.responses import from_openai_responses_response


def _reply(reason: str | None) -> dict[str, Any]:
    details = {"reason": reason} if reason is not None else None
    return {
        "id": "resp_1",
        "model": "gpt-model",
        "status": "incomplete",
        "incomplete_details": details,
        "output": [
            {
                "type": "message",
                "id": "m1",
                "status": "incomplete",
                "content": [{"type": "output_text", "text": "half"}],
            }
        ],
    }


def test_the_output_token_limit_is_translated() -> None:
    # spec.md fixes this direction, and it is the only one it fixes.
    assert from_openai_responses_response(_reply("max_output_tokens")).stop_reason == "max_tokens"


def test_any_other_reason_reaches_the_client_in_upstream_s_own_words() -> None:
    """It used to become `end_turn`, which told the client a turn upstream had cut short was one it finished.

    The streaming path stopped doing that on 2026-08-22; until this line the two paths gave different answers for the same upstream reply, which is worse than either answer alone.
    """
    assert from_openai_responses_response(_reply("content_filter")).stop_reason == "content_filter"


def test_an_incomplete_reply_that_gives_no_reason_still_does_not_read_as_finished() -> None:
    """Upstream said the reply is incomplete and did not say why, which is not the same as ending cleanly. `incomplete` is the `status` it sent."""
    assert from_openai_responses_response(_reply(None)).stop_reason == "incomplete"


def test_a_complete_reply_is_unaffected() -> None:
    """The control. Without it the rule above would pass just as well if it never said `end_turn` at all."""
    whole = _reply("max_output_tokens") | {"status": "completed", "incomplete_details": None}
    assert from_openai_responses_response(whole).stop_reason == "end_turn"


def _reply_with(*items: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "model": "gpt-model",
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": list(items),
    }


def _message(text: str, status: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": f"m_{text}",
        "status": status,
        "content": [{"type": "output_text", "text": text}],
    }


def test_the_item_upstream_cut_short_is_dropped_once_something_whole_came_before() -> None:
    """The same boundary the streaming assembler finds, found here instead because this path never sees an event.

    It has to be here rather than on the finished body: `status` is upstream's, and nothing carries it across the translation.
    """
    reply = from_openai_responses_response(_reply_with(_message("whole", "completed"), _message("half", "incomplete")))
    assert [b.text for b in reply.blocks] == ["whole"]


def test_the_item_upstream_cut_short_is_kept_when_it_is_all_there_is() -> None:
    """Half a sentence still beats an empty answer, so the rule reverses when this is all there is."""
    reply = from_openai_responses_response(_reply_with(_message("half", "incomplete")))
    assert [b.text for b in reply.blocks] == ["half"]


def test_a_whole_item_is_never_dropped_however_many_came_before() -> None:
    """The control: without it, a rule that dropped on position alone would pass the first test too."""
    reply = from_openai_responses_response(_reply_with(_message("one", "completed"), _message("two", "completed")))
    assert [b.text for b in reply.blocks] == ["one", "two"]


def test_a_buffered_ending_that_hands_over_nothing_keeps_the_block_it_cut_short() -> None:
    """The same rule as the streaming assembler reaches by a different route, because this path already knows why the reply is incomplete.

    Dropping a passage is only defensible when the client is handed a way to get it back. A `content_filter` ending is not carried on by default, so the passage stays — otherwise the client loses it for good, on a reply that looks like an ordinary one.
    """
    reply = _reply_with(_message("whole", "completed"), _message("half", "incomplete"))
    reply["incomplete_details"] = {"reason": "content_filter"}
    assert [b.text for b in from_openai_responses_response(reply).blocks] == ["whole", "half"]


def test_an_operator_can_say_a_filtered_turn_is_worth_carrying_on() -> None:
    """And then the drop comes with it, because the two are one setting."""
    reply = _reply_with(_message("whole", "completed"), _message("half", "incomplete"))
    reply["incomplete_details"] = {"reason": "content_filter"}
    translated = from_openai_responses_response(
        reply, hand_over_stop_reasons=frozenset({"content_filter"})
    )
    assert [b.text for b in translated.blocks] == ["whole"]
