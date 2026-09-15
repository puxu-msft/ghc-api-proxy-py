from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import app.tokenization.worker as worker_module
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.request import WireFormat
from app.tokenization.features import analyze_responses_input
from app.tokenization.learning import (
    TokenLearningService,
    descriptor_fingerprint,
)
from app.tokenization.learning_store import TokenLearningStore
from app.tokenization.types import LearningIdentity
from app.tokenization.worker import LocalTokenWorker


@pytest.fixture
def inline_token_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_sync(
        function: Callable[..., Any],
        *args: Any,
        **_kwargs: Any,
    ) -> Any:
        return function(*args)

    monkeypatch.setattr(worker_module, "run_sync", run_sync)


@pytest.mark.asyncio
async def test_learning_service_persists_same_attempt_body_and_usage(
    tmp_path: Path,
    inline_token_worker: None,
) -> None:
    payload = {
        "model": "gpt-model",
        "input": [{"type": "message", "role": "user", "content": "hello"}],
    }
    body = b'{"input":[{"content":"hello","role":"user","type":"message"}],"model":"gpt-model"}'
    descriptor = ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="ghc",
    )
    store_path = tmp_path / "learning.sqlite3"
    service = TokenLearningService(
        LocalTokenWorker(),
        store=TokenLearningStore(store_path),
    )

    await service.start()
    assert service.offer(
        request_id="request-1",
        attempt_index=0,
        body=body,
        actual_input_tokens=42,
        provider_name="ghc",
        resolved_model="gpt-model",
        endpoint=ModelEndpoint.OPENAI_RESPONSES,
        target_format=WireFormat.OPENAI_RESPONSES,
        descriptor=descriptor,
    )
    await service.close()

    features = analyze_responses_input(payload)
    identity = LearningIdentity(
        actual_provider="ghc",
        resolved_model="gpt-model",
        endpoint=ModelEndpoint.OPENAI_RESPONSES.value,
        wire_format=WireFormat.OPENAI_RESPONSES.value,
        tokenizer="o200k_base",
        descriptor_fingerprint=descriptor_fingerprint(descriptor),
        estimator_generation=features.estimator_generation,
        profile_schema_revision=features.profile_schema_revision,
        learning_epoch=0,
    )
    reopened = TokenLearningStore(store_path)
    await reopened.start()
    snapshot = await reopened.snapshot_for_prediction(identity)

    assert len(snapshot.samples) == 1
    assert snapshot.samples[0].actual_input_tokens == 42
    assert snapshot.samples[0].raw_body_sha256 == snapshot.samples[0].features.raw_sent_body_sha256
    assert len(snapshot.prediction_records) == 1
    await reopened.close()


@pytest.mark.asyncio
async def test_learning_service_selects_exact_history_for_a_repeated_count(
    tmp_path: Path,
    inline_token_worker: None,
) -> None:
    payload = {
        "model": "gpt-model",
        "input": [{"type": "message", "role": "user", "content": "hello"}],
    }
    body = b'{"input":[{"content":"hello","role":"user","type":"message"}],"model":"gpt-model"}'
    descriptor = ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="ghc",
    )
    service = TokenLearningService(
        LocalTokenWorker(),
        store=TokenLearningStore(tmp_path / "learning.sqlite3"),
    )

    await service.start()
    assert service.offer(
        request_id="request-1",
        attempt_index=0,
        body=body,
        actual_input_tokens=42,
        provider_name="ghc",
        resolved_model="gpt-model",
        endpoint=ModelEndpoint.OPENAI_RESPONSES,
        target_format=WireFormat.OPENAI_RESPONSES,
        descriptor=descriptor,
    )
    await service.flush()

    selected = await service.predict_responses(
        payload=payload,
        provider_name="ghc",
        resolved_model="gpt-model",
        endpoint=ModelEndpoint.OPENAI_RESPONSES,
        target_format=WireFormat.OPENAI_RESPONSES,
        descriptor=descriptor,
    )

    assert selected is not None
    assert selected.method.value == "history-exact"
    assert selected.unscaled_tokens == 42
    await service.close()
