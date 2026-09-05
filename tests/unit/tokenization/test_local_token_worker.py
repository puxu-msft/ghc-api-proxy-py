import asyncio
import json
from pathlib import Path

import anyio
import pytest
from prometheus_client import CollectorRegistry
from prompt_admission_process_helper import controlled_estimate

import app.tokenization.worker as worker_module
from app.models.anthropic import MessagesRequest
from app.observability.metrics import ResponsivenessMetrics
from app.pipeline.count_tokens import CountTokensRequestError
from app.tokenization.estimators import estimate_anthropic_input, estimate_responses_input
from app.tokenization.worker import LocalTokenWorker


@pytest.mark.parametrize("protocol", ["anthropic", "openai-responses"])
async def test_real_worker_keeps_counts_and_publishes_parent_metrics(
    protocol: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [{"role": "user", "content": "hello there"}]
    if protocol == "anthropic":
        payload = {"model": "model", "messages": messages}
        expected = estimate_anthropic_input(MessagesRequest.model_validate({**payload, "max_tokens": 1}))
    else:
        payload = {"model": "model", "input": [{"type": "message", **messages[0]}]}
        expected = estimate_responses_input(payload)
    registry = CollectorRegistry()
    metrics = ResponsivenessMetrics(registry)
    monkeypatch.setattr(worker_module, "RESPONSIVENESS", metrics)

    result = await LocalTokenWorker().estimate(protocol, payload)

    assert result == expected
    assert "max_tokens" not in payload
    format_name = "anthropic" if protocol == "anthropic" else "responses"
    for phase in ("lookup", "estimate"):
        labels = {"format": format_name, "phase": phase}
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_count", labels) == 1
        duration = registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_sum", labels)
        assert duration is not None and duration >= 0
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_max_seconds", labels) == duration
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_failures_total", labels) == 0


async def test_real_worker_propagates_validation_error_without_fake_metric_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = CollectorRegistry()
    monkeypatch.setattr(worker_module, "RESPONSIVENESS", ResponsivenessMetrics(registry))

    with pytest.raises(CountTokensRequestError, match="not a countable Messages body"):
        await LocalTokenWorker().estimate("anthropic", {"model": "model", "messages": "not messages"})

    assert registry.get_sample_value(
        "ghc_proxy_local_tokenizer_duration_seconds_count", {"format": "anthropic", "phase": "lookup"}
    ) == 0


async def test_real_worker_keeps_encoding_failure_and_stage_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = CollectorRegistry()
    monkeypatch.setattr(worker_module, "RESPONSIVENESS", ResponsivenessMetrics(registry))
    payload = {"model": "model", "input": [{"type": "message", "role": "user", "content": "<|endoftext|>"}]}

    with pytest.raises(ValueError, match="disallowed special token"):
        await LocalTokenWorker().estimate("openai-responses", payload)

    for phase, failures in (("lookup", 0), ("estimate", 1)):
        labels = {"format": "responses", "phase": phase}
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_count", labels) == 1
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_failures_total", labels) == failures


async def wait_for_file(file: Path) -> None:
    async with asyncio.timeout(5):
        while not file.exists():
            await asyncio.sleep(0.01)


def controlled_payload(directory: Path, name: str) -> tuple[dict[str, str], Path, Path]:
    entered = directory / f"{name}-entered"
    release = directory / f"{name}-release"
    text = json.dumps({"entered": str(entered), "release": str(release), "result": 17})
    return {"input": text}, entered, release


async def test_real_worker_can_be_cancelled_while_running_and_queued(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_module, "_estimate_input", controlled_estimate)
    limiter = anyio.CapacityLimiter(1)
    worker = LocalTokenWorker(limiter=limiter)
    payload_a, entered_a, release_a = controlled_payload(tmp_path, "a")
    payload_b, entered_b, release_b = controlled_payload(tmp_path, "b")
    first = asyncio.create_task(worker.estimate("openai-responses", payload_a))
    await wait_for_file(entered_a)
    second = asyncio.create_task(worker.estimate("openai-responses", payload_b))
    fallback_used = False

    async def fallback_release() -> None:
        nonlocal fallback_used
        await asyncio.sleep(3)
        fallback_used = True
        release_a.touch()
        release_b.touch()

    fallback = asyncio.create_task(fallback_release())
    try:
        async with asyncio.timeout(2):
            while limiter.statistics().tasks_waiting != 1:
                await asyncio.sleep(0)
        assert not entered_b.exists()
        assert not first.done()
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert limiter.borrowed_tokens == 1
        assert not entered_b.exists()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not fallback_used
        assert limiter.borrowed_tokens == 0
        release_b.touch()
        assert await asyncio.wait_for(worker.estimate("openai-responses", payload_b), timeout=5) == 17
        assert entered_b.exists()
    finally:
        release_a.touch()
        release_b.touch()
        first.cancel()
        second.cancel()
        fallback.cancel()
        # Collect expected task cancellation after releasing all barriers, including on assertion failure.
        await asyncio.gather(first, second, fallback, return_exceptions=True)
