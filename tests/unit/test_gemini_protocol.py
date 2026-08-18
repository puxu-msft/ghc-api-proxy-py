import pytest

from app.models.gemini import GenerateContentRequest
from app.protocols.gemini import (
    GeminiPathError,
    gemini_to_openai,
    parse_model_with_method,
)


def test_gemini_models_preserve_unknown_fields_recursively() -> None:
    request = GenerateContentRequest.model_validate(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "hi", "future_part": None}],
                    "future_content": True,
                }
            ],
            "future_request": {"x": 1},
        }
    )
    dumped = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped["future_request"] == {"x": 1}
    assert dumped["contents"][0]["parts"][0]["future_part"] is None


def test_gemini_path_splits_last_colon_and_rejects_method() -> None:
    assert parse_model_with_method("vendor:family:model:generateContent") == (
        "vendor:family:model",
        "generateContent",
    )
    with pytest.raises(GeminiPathError):
        parse_model_with_method("model:unknown")


def test_gemini_to_openai_maps_roles_system_and_generation_config() -> None:
    request = GenerateContentRequest.model_validate(
        {
            "systemInstruction": {"parts": [{"text": "rules"}]},
            "contents": [
                {"role": "user", "parts": [{"text": "hi"}]},
                {"role": "model", "parts": [{"text": "hello"}]},
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 50},
        }
    )
    converted = gemini_to_openai(request, model="gpt-test", stream=False)
    assert [message["role"] for message in converted["messages"]] == [
        "system",
        "user",
        "assistant",
    ]
    assert converted["temperature"] == 0.2
    assert converted["max_tokens"] == 50
