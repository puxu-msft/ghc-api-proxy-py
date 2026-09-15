import base64
import json

import tiktoken

from app.tokenization.estimators import estimate_commandcode_input
from app.tokenization.types import TokenizationCapabilities

ENCODING = tiktoken.get_encoding("o200k_base")


def ordinary(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


def envelope(params: dict[str, object]) -> dict[str, object]:
    return {
        "config": {"workingDir": "/workspace", "environment": "production"},
        "memory": None,
        "taste": None,
        "skills": "",
        "permissionMode": "standard",
        "params": params,
    }


def test_commandcode_estimator_counts_converted_messages_not_inbound_anthropic_shape() -> None:
    payload = envelope(
        {
            "model": "cc-model",
            "stream": True,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }
    )

    count = estimate_commandcode_input(payload)

    assert count >= ordinary("user") + ordinary("hello") + 8


def test_commandcode_image_carrier_is_not_encoded_as_ordinary_text() -> None:
    short = envelope(
        {
            "model": "cc-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": "data:image/png;base64,"
                            + base64.b64encode(b"x").decode(),
                        }
                    ],
                }
            ],
        }
    )
    long = json.loads(json.dumps(short))
    long["params"]["messages"][0]["content"][0]["image"] += base64.b64encode(
        b"x" * 10_000
    ).decode()

    assert estimate_commandcode_input(long) == estimate_commandcode_input(short)


def test_commandcode_placeholder_is_counted_only_when_the_capability_is_enabled() -> None:
    payload = envelope(
        {
            "model": "cc-model",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        }
    )

    without_placeholder = estimate_commandcode_input(payload)
    with_placeholder = estimate_commandcode_input(
        payload,
        capabilities=TokenizationCapabilities(
            commandcode_empty_system_placeholder=True
        ),
    )

    assert with_placeholder - without_placeholder == ordinary(" ") + 4
