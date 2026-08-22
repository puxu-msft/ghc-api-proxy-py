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
