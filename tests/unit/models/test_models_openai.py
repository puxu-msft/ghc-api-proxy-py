from app.models.openai import (
    ChatCompletionRequest,
    EmbeddingsRequest,
    ResponsesRequest,
)
from app.openai.responses_conversion import normalize_call_ids
from app.wire_json import JsonValue


def test_chat_request_preserves_nested_unknown_and_null_fields() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-test",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "future_part", "payload": {"x": 1}}],
                    "future_message": None,
                }
            ],
            "future_request": {"enabled": True},
        }
    )

    dumped = request.model_dump(mode="json", exclude_unset=True)
    assert dumped["messages"][0]["future_message"] is None
    assert dumped["messages"][0]["content"][0]["payload"] == {"x": 1}
    assert dumped["future_request"] == {"enabled": True}


def test_responses_request_preserves_polymorphic_input() -> None:
    request = ResponsesRequest.model_validate(
        {
            "model": "gpt-test",
            "input": [
                {
                    "type": "future_item",
                    "future": {"nested": True},
                    "nullable": None,
                }
            ],
        }
    )

    dumped = request.model_dump(mode="json", exclude_unset=True)
    assert dumped["input"][0]["future"] == {"nested": True}
    assert dumped["input"][0]["nullable"] is None


def test_embeddings_request_accepts_string_or_array_input() -> None:
    assert EmbeddingsRequest(model="embed", input="hello").input == "hello"
    assert EmbeddingsRequest(model="embed", input=["a", "b"]).input == ["a", "b"]


def test_normalize_call_ids_rewrites_call_prefix_recursively() -> None:
    value: JsonValue = {
        "id": "call_root",
        "output": [
            {"type": "function_call", "id": "call_item", "call_id": "call_item"},
            {"type": "function_call_output", "call_id": "call_item"},
        ],
    }

    assert normalize_call_ids(value) == {
        "id": "call_root",
        "output": [
            {"type": "function_call", "id": "fc_item", "call_id": "fc_item"},
            {"type": "function_call_output", "call_id": "fc_item"},
        ],
    }
