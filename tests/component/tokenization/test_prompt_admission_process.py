import asyncio
import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from prompt_admission_process_helper import controlled_count

import app.tokenization.admission as admission_module
from app.model_provider import ModelDescriptor, ModelEndpoint, PromptTokenLimits
from app.tokenization.admission import (
    OPENAI_RESPONSES,
    PromptTokenAdmission,
    TokenAdmissionOutcome,
)


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


@pytest.mark.real_process
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


@pytest.mark.real_process
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
