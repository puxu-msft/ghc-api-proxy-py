import asyncio
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import anyio
import pytest
import tiktoken
from prompt_admission_process_helper import controlled_count

import app.tokenization.admission as admission_module
from app.model_provider import ModelDescriptor, ModelEndpoint, PromptTokenLimits
from app.pipeline.translation_driver.anthropic_messages import from_anthropic_messages
from app.pipeline.translation_driver.openai_responses import to_openai_responses
from app.pipeline.translation_driver.semantic import TranslationTarget
from app.tokenization.admission import (
    OPENAI_RESPONSES,
    PromptTokenAdmission,
    TokenAdmissionOutcome,
)

ENCODING = tiktoken.get_encoding("o200k_base")


def descriptor(
    *,
    tokenizer: str = "o200k_base",
    prompt_limit: int | None = None,
    context_limit: int = 120,
) -> ModelDescriptor:
    return ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="ghc",
        catalog_generation=7,
        catalog_refreshed_at="2026-09-04T00:00:00+00:00",
        prompt_token_limits=PromptTokenLimits(
            tokenizer=tokenizer,
            max_prompt_tokens=context_limit if prompt_limit is None else prompt_limit,
            max_context_window_tokens=context_limit,
        ),
    )


def text_count(text: str) -> int:
    return len(ENCODING.encode_ordinary(text))


@pytest.mark.asyncio
async def test_a_single_field_over_the_context_limit_is_rejected_but_equality_is_admitted() -> None:
    text = "abcdefghij " * 200
    count = text_count(text)
    policy = PromptTokenAdmission()

    rejected = await policy.evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload={"model": "gpt-model", "input": text},
    )
    admitted = await policy.evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count, context_limit=count),
        payload={"model": "gpt-model", "input": text},
    )

    assert rejected.outcome is TokenAdmissionOutcome.REJECTED
    assert rejected.field_path == "input"
    assert rejected.field_token_count == count
    assert admitted.outcome is TokenAdmissionOutcome.ADMITTED_COUNTED
    assert admitted.field_token_count == count


@pytest.mark.asyncio
async def test_fields_are_never_added_together_for_admission() -> None:
    first = "alpha " * 120
    second = "bravo " * 120
    limit = max(text_count(first), text_count(second))
    assert text_count(first) + text_count(second) > limit

    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=limit, context_limit=limit),
        payload={
            "model": "gpt-model",
            "input": [
                {"type": "message", "role": "user", "content": first},
                {"type": "message", "role": "assistant", "content": second},
            ],
        },
    )

    assert observed.outcome is TokenAdmissionOutcome.ADMITTED_COUNTED
    assert observed.field_token_count == limit


@pytest.mark.asyncio
async def test_every_byte_eligible_field_is_counted_not_only_the_largest() -> None:
    low_density = "a" * 2000
    high_density = "".join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(28))
    assert len(low_density.encode()) > len(high_density.encode())
    assert text_count(low_density) < 1000 < text_count(high_density)

    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=900, context_limit=1000),
        payload={
            "model": "gpt-model",
            "input": [
                {"type": "message", "role": "user", "content": low_density},
                {"type": "message", "role": "user", "content": high_density},
            ],
        },
    )

    assert observed.outcome is TokenAdmissionOutcome.REJECTED
    assert observed.field_path == "input[1].content"
    assert observed.field_token_count == text_count(high_density)


@pytest.mark.asyncio
async def test_incident_additional_tools_role_is_an_approved_shape() -> None:
    text = "0123456789" * 100
    count = text_count(text)
    payload: dict[str, Any] = {
        "model": "gpt-model",
        "input": [
            {"type": "additional_tools", "id": "tools_1", "role": "developer", "tools": []},
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    }

    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload=payload,
    )
    unknown = deepcopy(payload)
    unknown["input"][0]["future_control"] = True
    skipped = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload=unknown,
    )

    assert observed.outcome is TokenAdmissionOutcome.REJECTED
    assert skipped.outcome is TokenAdmissionOutcome.SKIPPED_UNKNOWN_SHAPE


@pytest.mark.asyncio
async def test_translated_tool_history_remains_in_the_admission_domain() -> None:
    text = "abcdefghij " * 100
    count = text_count(text)
    payload: dict[str, Any] = {
        "model": "gpt-model",
        "input": [
            {"type": "function_call", "call_id": "call_1", "name": "Read", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "call_1", "output": "done"},
            {"type": "reasoning", "summary": [], "encrypted_content": "opaque"},
            {
                "type": "tool_search_call",
                "call_id": "search_1",
                "arguments": {},
                "execution": "client",
                "status": "completed",
            },
            {
                "type": "tool_search_output",
                "call_id": "search_1",
                "execution": "client",
                "status": "completed",
                "tools": [],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    }

    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload=payload,
    )

    assert observed.outcome is TokenAdmissionOutcome.REJECTED
    assert observed.field_path == "input[5].content[0].text"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-model", "input": "x", "truncation": "auto"},
        {
            "model": "gpt-model",
            "input": "x",
            "context_management": [{"type": "compaction", "compact_threshold": 10}],
        },
        {"model": "gpt-model", "input": [{"type": "compaction", "encrypted_content": "x"}]},
        {"model": "gpt-model", "input": [{"type": "compaction_trigger"}]},
    ],
)
async def test_upstream_owned_reduction_controls_fail_open(payload: dict[str, Any]) -> None:
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(context_limit=1),
        payload=payload,
    )

    assert observed.outcome is TokenAdmissionOutcome.SKIPPED_REDUCTION_CONTROL
    assert observed.field_path is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-model", "input": "x", "future_control": True},
        {"model": "gpt-model", "input": [{"type": "future_item", "text": "x"}]},
        {
            "model": "gpt-model",
            "input": [{"type": "message", "role": "user", "content": "x", "future": True}],
        },
        {
            "model": "gpt-model",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "future_part", "text": "x"}],
                }
            ],
        },
        {
            "model": "gpt-model",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "x", "future": True}],
                }
            ],
        },
    ],
)
async def test_unknown_shapes_fail_open(payload: dict[str, Any]) -> None:
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(context_limit=1),
        payload=payload,
    )

    assert observed.outcome is TokenAdmissionOutcome.SKIPPED_UNKNOWN_SHAPE


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["x", "x" * 1000])
async def test_unsupported_tokenizer_is_named_before_the_byte_fast_path(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> None:
    async def must_not_run(*_: Any, **__: Any) -> int:
        raise AssertionError("unsupported tokenizer must not start a worker")

    monkeypatch.setattr(admission_module, "run_sync", must_not_run)
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(tokenizer="future_encoding", context_limit=10),
        payload={"model": "gpt-model", "input": text},
    )

    assert observed.outcome is TokenAdmissionOutcome.SKIPPED_UNSUPPORTED_TOKENIZER
    assert observed.tokenizer == "future_encoding"
    assert observed.field_path is None


@pytest.mark.asyncio
async def test_non_lookup_worker_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_: Any, **__: Any) -> int:
        raise RuntimeError("worker failed")

    monkeypatch.setattr(admission_module, "run_sync", fail)
    with pytest.raises(RuntimeError, match="worker failed"):
        await PromptTokenAdmission().evaluate(
            attempt=0,
            target_format=OPENAI_RESPONSES,
            descriptor=descriptor(context_limit=1),
            payload={"model": "gpt-model", "input": "long enough"},
        )


def process_control(tmp_path: Path, name: str, *, released: bool = False) -> tuple[str, Path, Path]:
    entered = tmp_path / f"{name}-entered"
    release = tmp_path / f"{name}-release"
    if released:
        release.write_text("go", encoding="utf-8")
    text = json.dumps(
        {
            "entered": str(entered),
            "release": str(release),
            "result": 2,
        }
    )
    return text, entered, release


@pytest.mark.asyncio
async def test_real_process_cancellation_releases_capacity_for_the_next_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admission_module, "_count_ordinary", controlled_count)
    real_run_sync = admission_module.run_sync
    limiter = anyio.CapacityLimiter(1)
    calls: list[tuple[bool, anyio.CapacityLimiter | None]] = []

    async def observed_run_sync(
        function: Any,
        *args: Any,
        cancellable: bool = False,
        limiter: anyio.CapacityLimiter | None = None,
    ) -> Any:
        calls.append((cancellable, limiter))
        return await real_run_sync(
            function,
            *args,
            cancellable=cancellable,
            limiter=limiter,
        )

    monkeypatch.setattr(admission_module, "run_sync", observed_run_sync)
    policy = PromptTokenAdmission(limiter=limiter)
    model = descriptor(context_limit=1)
    first_text, first_entered, first_release = process_control(tmp_path, "first")
    first = asyncio.create_task(
        policy.evaluate(
            attempt=0,
            target_format=OPENAI_RESPONSES,
            descriptor=model,
            payload={"model": "gpt-model", "input": first_text},
        )
    )
    async with asyncio.timeout(5):
        while not first_entered.exists():
            await asyncio.sleep(0.01)

    fallback_used = False

    async def fallback_release() -> None:
        nonlocal fallback_used
        await asyncio.sleep(1)
        fallback_used = True
        first_release.write_text("go", encoding="utf-8")

    fallback = asyncio.create_task(fallback_release())
    try:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    finally:
        fallback.cancel()
        first_release.write_text("go", encoding="utf-8")
        await asyncio.gather(first, fallback, return_exceptions=True)

    assert fallback_used is False
    assert limiter.borrowed_tokens == 0
    second_text, second_entered, _ = process_control(tmp_path, "second", released=True)
    observed = await asyncio.wait_for(
        policy.evaluate(
            attempt=1,
            target_format=OPENAI_RESPONSES,
            descriptor=model,
            payload={"model": "gpt-model", "input": second_text},
        ),
        timeout=5,
    )
    assert observed.outcome is TokenAdmissionOutcome.REJECTED
    assert second_entered.exists()
    assert calls and all(cancellable is True and used is limiter for cancellable, used in calls)


@pytest.mark.asyncio
async def test_real_process_counts_share_one_worker_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admission_module, "_count_ordinary", controlled_count)
    limiter = anyio.CapacityLimiter(1)
    policy = PromptTokenAdmission(limiter=limiter)
    model = descriptor(context_limit=1)
    first_text, first_entered, first_release = process_control(tmp_path, "first")
    second_text, second_entered, second_release = process_control(tmp_path, "second")
    first = asyncio.create_task(
        policy.evaluate(
            attempt=0,
            target_format=OPENAI_RESPONSES,
            descriptor=model,
            payload={"model": "gpt-model", "input": first_text},
        )
    )
    second = asyncio.create_task(
        policy.evaluate(
            attempt=1,
            target_format=OPENAI_RESPONSES,
            descriptor=model,
            payload={"model": "gpt-model", "input": second_text},
        )
    )
    try:
        async with asyncio.timeout(5):
            while not (
                limiter.statistics().tasks_waiting == 1
                and int(first_entered.exists()) + int(second_entered.exists()) == 1
            ):
                await asyncio.sleep(0.01)
        assert limiter.borrowed_tokens == 1

        if first_entered.exists():
            first_release.write_text("go", encoding="utf-8")
        else:
            second_release.write_text("go", encoding="utf-8")
        async with asyncio.timeout(5):
            while not (first_entered.exists() and second_entered.exists()):
                await asyncio.sleep(0.01)
    finally:
        first_release.write_text("go", encoding="utf-8")
        second_release.write_text("go", encoding="utf-8")
        await asyncio.gather(first, second, return_exceptions=True)

    assert limiter.borrowed_tokens == 0


def translated_image_payload(image: dict[str, Any], text: str) -> dict[str, Any]:
    semantic = from_anthropic_messages(
        {
            "model": "gpt-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        image,
                    ],
                }
            ],
        }
    )
    return to_openai_responses(
        semantic,
        TranslationTarget(model_id="gpt-model"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image",
    [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": "AAAA"},
        }
        for media_type in ("image/jpeg", "image/png", "image/gif", "image/webp")
    ]
    + [
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.invalid/image.png"},
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        {
            "type": "image",
            "source": {"type": "file", "file_id": "file_1"},
            "transformations": {"oversized_image": "downsize"},
        },
        {
            "type": "image",
            "source": {"type": "file", "file_id": "file_2"},
            "cache_control": None,
            "transformations": None,
        },
    ],
    ids=["jpeg", "png", "gif", "webp", "url-cache", "file-transform", "nullable-metadata"],
)
async def test_real_translator_native_image_shapes_remain_in_the_admission_domain(
    image: dict[str, Any],
) -> None:
    text = "abcdefghij " * 100
    count = text_count(text)
    payload = translated_image_payload(image, text)

    assert [item["type"] for item in payload["input"]] == ["message", "image"]
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload=payload,
    )

    assert observed.outcome is TokenAdmissionOutcome.REJECTED
    assert observed.field_path == "input[0].content[0].text"
    assert observed.field_token_count == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image",
    [
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.invalid/image.png"},
            "future": True,
        },
        {"type": "image", "source": {"type": "future", "url": "https://example.invalid"}},
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.invalid/image.png",
                "future": True,
            },
        },
        {"type": "image", "source": {"type": "url", "url": 7}},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "application/pdf", "data": "AAAA"},
        },
        {
            "type": "image",
            "source": {"type": "base64", "media_type": [], "data": "AAAA"},
        },
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.invalid/image.png"},
            "cache_control": {"type": "ephemeral", "ttl": "2h"},
        },
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.invalid/image.png"},
            "cache_control": {"type": "ephemeral", "ttl": []},
        },
        {
            "type": "image",
            "source": {"type": "file", "file_id": "file_1"},
            "transformations": {"oversized_image": "crop"},
        },
        {
            "type": "image",
            "source": {"type": "file", "file_id": "file_1"},
            "transformations": {"oversized_image": []},
        },
    ],
    ids=[
        "unknown-outer",
        "unknown-source-type",
        "unknown-source-field",
        "wrong-required-type",
        "invalid-media-type",
        "unhashable-media-type",
        "invalid-cache-ttl",
        "unhashable-cache-ttl",
        "invalid-transformation",
        "unhashable-transformation",
    ],
)
async def test_real_translator_unknown_or_malformed_native_images_fail_open(
    image: dict[str, Any],
) -> None:
    text = "abcdefghij " * 100
    count = text_count(text)
    payload = translated_image_payload(image, text)

    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(prompt_limit=count - 2, context_limit=count - 1),
        payload=payload,
    )

    assert observed.outcome is TokenAdmissionOutcome.SKIPPED_UNKNOWN_SHAPE
    assert observed.field_path is None


@pytest.mark.asyncio
async def test_native_image_and_encrypted_reasoning_are_not_counted_as_text() -> None:
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=descriptor(context_limit=1),
        payload={
            "model": "gpt-model",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_image", "image_url": "data:image/png;base64," + "A" * 1000}],
                },
                {"type": "reasoning", "summary": [], "encrypted_content": "A" * 1000},
            ],
        },
    )

    assert observed.outcome is TokenAdmissionOutcome.ADMITTED_FAST
    assert observed.field_path is None


@pytest.mark.asyncio
async def test_non_responses_attempt_is_not_applicable() -> None:
    observed = await PromptTokenAdmission().evaluate(
        attempt=2,
        target_format="anthropic-messages",
        descriptor=descriptor(),
        payload={"model": "gpt-model", "messages": []},
    )

    assert observed.outcome is TokenAdmissionOutcome.NOT_APPLICABLE
    assert observed.attempt == 2
    assert observed.tokenizer is None
    assert observed.max_context_window_tokens is None


@pytest.mark.asyncio
async def test_missing_metadata_has_a_complete_nullable_observation() -> None:
    observed = await PromptTokenAdmission().evaluate(
        attempt=0,
        target_format=OPENAI_RESPONSES,
        descriptor=ModelDescriptor(
            id="gpt-model",
            endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
            provider_name="ghc",
            catalog_generation=3,
        ),
        payload={"model": "gpt-model", "input": "x"},
    )

    assert observed.outcome is TokenAdmissionOutcome.SKIPPED_MISSING_METADATA
    assert observed.tokenizer is None
    assert observed.max_prompt_tokens is None
    assert observed.max_context_window_tokens is None
    assert observed.field_path is None
    assert observed.field_token_count is None
