from app.tokenization.limits import PromptLimitRegistry, parse_prompt_limit_error


def test_parse_supported_prompt_limit_errors_from_text_and_json() -> None:
    first = parse_prompt_limit_error(
        "prompt token count of 150000 exceeds the limit of 100000"
    )
    second = parse_prompt_limit_error(
        '{"error":{"message":"prompt is too long: 200000 tokens > 168000 maximum"}}'
    )

    assert first == (150_000, 100_000)
    assert second == (200_000, 168_000)


def test_ignore_invalid_or_non_limit_errors() -> None:
    assert parse_prompt_limit_error("bad request") is None
    assert parse_prompt_limit_error("prompt is too long: 10 tokens > 20 maximum") is None
    assert parse_prompt_limit_error('{"error":{"message":7}}') is None


def test_registry_records_observation_without_overwriting_catalog_value() -> None:
    registry = PromptLimitRegistry()
    registry.record(
        "anthropic",
        "Claude-Opus-4.8",
        current=200_000,
        limit=168_000,
        source="anthropic_messages_error",
        observed_at=10.0,
    )
    registry.record(
        "anthropic",
        "claude-opus-4-8",
        current=201_000,
        limit=168_000,
        source="anthropic_messages_error",
        observed_at=20.0,
    )

    item = registry.get("anthropic", "claude-opus-4.8")
    assert item is not None
    assert item.observed_limit == 168_000
    assert item.observed_input_tokens == 201_000
    assert item.observation_count == 2
    assert item.observed_at == 20.0
