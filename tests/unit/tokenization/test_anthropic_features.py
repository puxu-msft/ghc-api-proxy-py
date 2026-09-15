import base64
from collections.abc import Mapping, Sequence

import tiktoken

from app.models.anthropic import MessagesRequest
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.types import SyntheticUnresizedPatchGridFormula, TokenizationCapabilities

ENCODING = tiktoken.get_encoding("o200k_base")


def ordinary(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


def request(messages: Sequence[Mapping[str, object]]) -> MessagesRequest:
    return MessagesRequest.model_validate(
        {"model": "claude-test", "max_tokens": 32, "messages": messages}
    )


def test_current_assistant_thinking_is_counted_as_visible_input() -> None:
    without_thinking = request([{"role": "assistant", "content": [{"type": "text", "text": "answer"}]}])
    with_thinking = request(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "internal plan", "signature": "opaque"},
                    {"type": "text", "text": "answer"},
                ],
            }
        ]
    )

    assert estimate_anthropic_input(with_thinking) > estimate_anthropic_input(without_thinking)
    assert estimate_anthropic_input(with_thinking) - estimate_anthropic_input(without_thinking) >= ordinary(
        "internal plan"
    )


def test_last_turn_only_thinking_mode_excludes_older_assistant_thinking() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "older plan"}],
        },
        {
            "role": "user",
            "content": "continue",
        },
        {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "current plan"}],
        },
    ]
    all_thinking = estimate_anthropic_input(
        request(messages),
        capabilities=TokenizationCapabilities(anthropic_thinking_mode="keep_all"),
    )
    last_only = estimate_anthropic_input(
        request(messages),
        capabilities=TokenizationCapabilities(anthropic_thinking_mode="last_turn_only"),
    )

    assert all_thinking - last_only >= ordinary("older plan")


def test_tool_identity_and_nested_tool_result_text_are_counted() -> None:
    plain = request([{"role": "user", "content": "run it"}])
    with_tool = request(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "lookup",
                        "input": {"city": "Seattle"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "is_error": False,
                        "content": [{"type": "text", "text": "rain"}],
                    }
                ],
            },
        ]
    )

    assert estimate_anthropic_input(with_tool) > estimate_anthropic_input(plain)


def test_image_carrier_size_does_not_become_ordinary_text_tokens() -> None:
    short = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(b"x").decode(),
        },
    }
    long = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(b"x" * 10_000).decode(),
        },
    }

    short_count = estimate_anthropic_input(request([{"role": "user", "content": [short]}]))
    long_count = estimate_anthropic_input(request([{"role": "user", "content": [long]}]))

    assert long_count == short_count


def test_image_capability_uses_dimensions_not_encoded_bytes() -> None:
    capabilities = TokenizationCapabilities(
        visual_formula=SyntheticUnresizedPatchGridFormula(1, 28, 28)
    )
    image = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(b"x").decode(),
            "width": 56,
            "height": 84,
        },
    }

    without = estimate_anthropic_input(request([{"role": "user", "content": [image]}]))
    with_capability = estimate_anthropic_input(
        request([{"role": "user", "content": [image]}]),
        capabilities=capabilities,
    )

    assert with_capability - without == 6
