"""What a non-streaming Responses reply says about why it stopped, in both directions.

The same rule the streaming assembler follows, held here so the two paths cannot describe one fact differently: the output-token limit is the only reason with an Anthropic spelling, and it is the only one translated.

The second half of the file is the reverse crossing — an Anthropic `stop_reason` rendered for a `/responses` client — which is the same rule read backwards and shares the streaming framer's two tables.
"""

from typing import Any

import pytest

from app.pipeline.translation_driver.responses import (
    SemanticResponse,
    from_openai_responses_response,
    to_openai_responses_response,
)


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
    # `.dev/docs/anthropic-responses-bridge/spec.md` fixes this direction, and it is the only one it fixes.
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


def _rendered(stop_reason: str) -> dict[str, Any]:
    """The reverse crossing: what a `/responses` client is handed for an Anthropic reply that stopped this way."""
    return to_openai_responses_response(
        SemanticResponse(id="msg_1", model="claude-model", stop_reason=stop_reason)
    )


# Every `stop_reason` that can reach the writer, and what the Responses vocabulary has for it. The Anthropic six are the ones Claude Code itself compares against (`.dev/docs/upstream/retry-and-continuation/reports/260821-upstream-termination-reasons.md` §2.3 counted the literals); `incomplete` is this proxy's own synthesis for an upstream that said the reply was cut short without saying why. `incomplete_details.reason` is an enumeration of `max_output_tokens` and `content_filter` only (openai SDK 3.3.1), so everything but the token limit crosses as a null reason.
_TERMINAL_STATE = [
    ("end_turn", "completed", None),
    ("tool_use", "completed", None),
    ("max_tokens", "incomplete", {"reason": "max_output_tokens"}),
    ("refusal", "incomplete", None),
    ("pause_turn", "incomplete", None),
    ("stop_sequence", "incomplete", None),
    ("model_context_window_exceeded", "incomplete", None),
    ("incomplete", "incomplete", None),
]


@pytest.mark.parametrize(("stop_reason", "status", "details"), _TERMINAL_STATE)
def test_each_stop_reason_crosses_to_one_terminal_state(
    stop_reason: str, status: str, details: dict[str, str] | None
) -> None:
    """The table itself, pinned. Both halves of the answer, because either alone can be right while the reply as a whole is wrong."""
    rendered = _rendered(stop_reason)
    assert (rendered["status"], rendered["incomplete_details"]) == (status, details)


def test_a_refusal_is_not_reported_as_a_finished_turn() -> None:
    """It used to be. `status` was a single comparison against `max_tokens`, so every other way a turn can be cut short said `completed` — the shape `fef7d96` removed from the other direction, still standing in this one.

    Named separately from the table above because this is the defect, and a table row can be deleted by someone who thinks it is redundant.
    """
    assert _rendered("refusal")["status"] == "incomplete"


def test_the_token_limit_now_says_why_it_stopped() -> None:
    """`incomplete` was already right here; `incomplete_details` was never emitted at all, so the one ending that did say it was cut short never said why."""
    assert _rendered("max_tokens")["incomplete_details"] == {"reason": "max_output_tokens"}


def test_the_field_is_always_present_even_on_a_finished_turn() -> None:
    """Absent and null are not the same thing to a client. Upstream's own bodies carry the key with a null on a reply that is going fine, and a reader that has to tell "no reason given" from "this proxy forgot the field" cannot do it from a missing key."""
    assert "incomplete_details" in _rendered("end_turn")


def test_a_filtered_turn_carries_its_reason_back_out() -> None:
    """The one reason that crosses both ways without translation, and the one this table used to drop.

    The reader keeps upstream's own word whenever there is no Anthropic spelling for it, so a filtered turn reaches the record already saying `content_filter` — which happens to be a term the Responses enumeration itself defines. Before the identity row existed the forward table had no entry for it and wrote null, so a client that upstream had told *why* its turn stopped got back only *that* it stopped.

    This is not the `refusal` question next door. Nothing is being mapped onto anything: the word arrived from this vocabulary and is going home to it.
    """
    assert _rendered("content_filter")["status"] == "incomplete"
    assert _rendered("content_filter")["incomplete_details"] == {"reason": "content_filter"}


def test_a_finished_turn_is_unaffected() -> None:
    """The control for the two above. It stays green under the rule they replace, which is what makes them evidence about `refusal` rather than about the function running at all."""
    assert _rendered("end_turn")["status"] == "completed"
    assert _rendered("tool_use")["status"] == "completed"
