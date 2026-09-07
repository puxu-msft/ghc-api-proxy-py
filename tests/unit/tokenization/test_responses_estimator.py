"""Regression tests for the Responses estimator's compatibility integer interface.

Delta tests protect individual known-text contributions. Independent ordinary-token and literal-framing expectations protect complete arithmetic and special-spelling semantics without using the production analyzer as their oracle.
"""

import json
from typing import Any

import pytest
import tiktoken

from app.tokenization.estimators import estimate_responses_input
from app.tokenization.features import analyze_responses_input
from app.tokenization.types import FeatureName

ENCODING = "o200k_base"
SPECIAL_SPELLINGS = sorted(tiktoken.get_encoding(ENCODING).special_tokens_set)


def tokens(text: str) -> int:
    return len(tiktoken.get_encoding(ENCODING).encode(text, disallowed_special=()))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def base() -> dict[str, Any]:
    return {
        "model": "gpt-model",
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        ],
    }


def test_reasoning_ciphertext_contributes_framing_and_opaque_features_not_text_tokens() -> None:
    short_payload = base()
    short_payload["input"].append(
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "A"}
    )
    long_payload = base()
    long_payload["input"].append(
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "A" * 4000}
    )

    short = analyze_responses_input(short_payload)
    long = analyze_responses_input(long_payload)

    assert short.known_tokens - analyze_responses_input(base()).known_tokens == 4
    assert long.known_tokens == short.known_tokens
    assert long.feature_vector.get(FeatureName.OPAQUE_REASONING_BYTES).value == 4000


def test_the_arguments_of_a_function_call_are_counted() -> None:
    payload = base()
    arguments = '{"path": "' + "a/" * 500 + '"}'
    payload["input"].append(
        {"type": "function_call", "call_id": "c1", "name": "Read", "arguments": arguments}
    )

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens(arguments)


def test_the_output_of_a_tool_result_is_counted() -> None:
    payload = base()
    output = "line\n" * 400
    payload["input"].append({"type": "function_call_output", "call_id": "c1", "output": output})

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens(output)


def test_instructions_are_counted() -> None:
    payload = base()
    payload["instructions"] = "be brief. " * 300

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens(payload["instructions"])


def test_a_tool_declaration_is_counted() -> None:
    payload = base()
    payload["tools"] = [
        {"type": "function", "name": "Read", "description": "d" * 2000, "parameters": {}}
    ]

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens("d" * 2000)


def test_an_item_of_an_unknown_kind_contributes_framing_and_features_not_blob_tokens() -> None:
    short_payload = base()
    short_payload["input"].append({"type": "something_new", "blob": "z"})
    long_payload = base()
    long_payload["input"].append({"type": "something_new", "blob": "z" * 3000})

    short = analyze_responses_input(short_payload)
    long = analyze_responses_input(long_payload)

    assert short.known_tokens - analyze_responses_input(base()).known_tokens == 4
    assert long.known_tokens == short.known_tokens
    assert long.feature_vector.get(FeatureName.UNKNOWN_JSON_BYTES).value > short.feature_vector.get(
        FeatureName.UNKNOWN_JSON_BYTES
    ).value


def test_the_text_of_a_message_is_counted() -> None:
    payload = base()
    said = "hello there. " * 300
    payload["input"].append(
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": said}]}
    )

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens(said)


def _special_surface(surface: str, spelling: str) -> tuple[dict[str, Any], int]:
    if surface == "instructions":
        return {"instructions": spelling}, tokens(spelling) + 4
    if surface == "message":
        return {"input": [{"type": "message", "role": "user", "content": spelling}]}, tokens(
            "user"
        ) + tokens(spelling) + 4
    if surface == "tool-schema":
        tool = {
            "type": "function",
            "name": "lookup",
            "parameters": {"type": "object", "description": spelling},
        }
        return {"tools": [tool]}, tokens(canonical([tool])) + 8
    if surface == "function-call-arguments":
        return {
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": spelling,
                }
            ]
        }, tokens("call_1") + tokens("lookup") + tokens(spelling) + 4
    if surface == "function-call-output":
        return {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": spelling,
                }
            ]
        }, tokens("call_1") + tokens(spelling) + 4
    raise AssertionError(f"unknown test surface: {surface}")


def test_configured_special_spellings_include_the_reported_input() -> None:
    assert "<|endoftext|>" in SPECIAL_SPELLINGS


@pytest.mark.parametrize("spelling", SPECIAL_SPELLINGS)
@pytest.mark.parametrize(
    "surface",
    [
        "instructions",
        "message",
        "tool-schema",
        "function-call-arguments",
        "function-call-output",
    ],
)
def test_configured_special_spellings_are_ordinary_text_on_every_responses_surface(
    spelling: str,
    surface: str,
) -> None:
    payload, expected = _special_surface(surface, spelling)

    assert estimate_responses_input(payload) == expected


def test_an_empty_body_still_counts_as_something() -> None:
    # Zero would divide badly in the calibrator and reads as "this request is free", which no request is.
    assert estimate_responses_input({}) >= 1
