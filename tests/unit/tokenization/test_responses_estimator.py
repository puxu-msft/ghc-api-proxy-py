"""What the Responses estimator counts, asserted by what changes when a part is added.

Written as deltas rather than absolute numbers on purpose. An absolute expectation would have to restate the formula, and a test that restates the thing it tests passes for every version of it — which is exactly how the first attempt at pinning this function failed: it asserted the handler's answer equalled `estimate_responses_input(...)`, which pins *which* estimator runs and nothing about what it computes. Three separate mutations to the estimator left the whole suite green.

Each test here corresponds to one such mutation: drop the piece it adds, and this goes red.
"""

from typing import Any

import pytest
import tiktoken

from app.tokenization.estimators import estimate_responses_input
from app.wire_json import dumps

ENCODING = "o200k_base"
SPECIAL_SPELLINGS = sorted(tiktoken.get_encoding(ENCODING).special_tokens_set)


def tokens(text: str) -> int:
    return len(tiktoken.get_encoding(ENCODING).encode(text, disallowed_special=()))


def base() -> dict[str, Any]:
    return {
        "model": "gpt-model",
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
        ],
    }


def test_a_reasoning_item_is_not_free() -> None:
    """The defect this file was written for.

    A measured round trip carried 7286 characters of `encrypted_content` in one reasoning item, and the 7.6 KB body it belonged to was reported as 30 tokens. Nothing corrects that afterwards — no learner teaches this protocol's calibration yet — so a zero here reaches the client as a zero.
    """
    payload = base()
    carrier = "A" * 4000
    payload["input"].append({"type": "reasoning", "id": "rs_1", "encrypted_content": carrier})

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens(carrier)


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


def test_an_item_of_an_unknown_kind_is_not_free() -> None:
    # A kind nobody has taught this function about must not read as weightless, or the next one upstream invents arrives as a body that measured smaller than it is.
    payload = base()
    payload["input"].append({"type": "something_new", "blob": "z" * 3000})

    grew_by = estimate_responses_input(payload) - estimate_responses_input(base())

    assert grew_by >= tokens("z" * 3000)


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
        text = f"user\n{spelling}"
        return {"input": [{"type": "message", "role": "user", "content": spelling}]}, tokens(text) + 4
    if surface == "tool-schema":
        tool = {
            "type": "function",
            "name": "lookup",
            "parameters": {"type": "object", "description": spelling},
        }
        return {"tools": [tool]}, tokens(dumps([tool]).decode()) + 4
    if surface == "function-call-arguments":
        text = f"call_1\nlookup\n{spelling}"
        return {
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": spelling,
                }
            ]
        }, tokens(text) + 4
    if surface == "function-call-output":
        text = f"call_1\n{spelling}"
        return {
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": spelling,
                }
            ]
        }, tokens(text) + 4
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
