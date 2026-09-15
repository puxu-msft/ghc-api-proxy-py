"""Background learning from actual Responses attempts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast
from uuid import uuid4

from app.model_provider.types import ModelDescriptor, ModelEndpoint
from app.pipeline.request import WireFormat
from app.tokenization.features import TOKENIZER_NAME
from app.tokenization.learning_store import TokenLearningStore
from app.tokenization.prediction import (
    build_prediction_record,
    evaluate,
    predict_exact_or_prefix,
)
from app.tokenization.types import (
    LearningIdentity,
    LearningSnapshot,
    LearningUpdate,
    NoPrefixCheckpointChange,
    StoredSample,
    TokenPrediction,
)
from app.wire_json import dumps, loads

logger = logging.getLogger(__name__)

_PROCESS_BOOT_ID = uuid4().hex


@dataclass(frozen=True, slots=True)
class TokenLearningOffer:
    request_id: str
    attempt_index: int
    body: bytes
    actual_input_tokens: int
    provider_name: str
    resolved_model: str
    endpoint: ModelEndpoint
    target_format: WireFormat
    descriptor: ModelDescriptor
    observed_at_us: int


def descriptor_fingerprint(descriptor: ModelDescriptor) -> str:
    limits = descriptor.prompt_token_limits
    capabilities = descriptor.tokenization_capabilities
    formula = capabilities.visual_formula if capabilities is not None else None
    payload = {
        "id": descriptor.id,
        "endpoints": sorted(endpoint.value for endpoint in descriptor.endpoints),
        "reasoning_efforts": descriptor.reasoning_efforts,
        "adaptive_thinking": descriptor.adaptive_thinking,
        "prompt_token_limits": (
            {
                "tokenizer": limits.tokenizer,
                "max_prompt_tokens": limits.max_prompt_tokens,
                "max_context_window_tokens": limits.max_context_window_tokens,
            }
            if limits is not None
            else None
        ),
        "tokenization_capabilities": (
            {
                "anthropic_thinking_mode": capabilities.anthropic_thinking_mode,
                "commandcode_empty_system_placeholder": (
                    capabilities.commandcode_empty_system_placeholder
                ),
                "visual_formula": (
                    {
                        "kind": formula.kind.value,
                        "revision": formula.revision,
                        "patch_width": formula.patch_width,
                        "patch_height": formula.patch_height,
                    }
                    if formula is not None
                    else None
                ),
            }
            if capabilities is not None
            else None
        ),
    }
    return hashlib.sha256(dumps(payload)).hexdigest()


class TokenLearningService:
    """Queue actual Responses usage for prediction and persistent learning."""

    def __init__(
        self,
        worker: Any,
        *,
        store: TokenLearningStore | None = None,
        max_items: int = 64,
        max_body_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if max_items < 1 or max_body_bytes < 1:
            raise ValueError("learning queue limits must be positive")
        self._worker = worker
        self._store = store or TokenLearningStore()
        self._max_items = max_items
        self._max_body_bytes = max_body_bytes
        self._queue: asyncio.Queue[TokenLearningOffer | None] = asyncio.Queue(maxsize=max_items)
        self._pending_body_bytes = 0
        self._task: asyncio.Task[None] | None = None
        self._anchor_tasks: set[asyncio.Task[None]] = set()
        self._state = "new"

    @property
    def store(self) -> TokenLearningStore:
        return self._store

    async def start(self) -> None:
        if self._state == "running":
            return
        if self._state != "new":
            raise RuntimeError(f"learning service cannot start from {self._state}")
        await self._store.start()
        self._state = "running"
        self._task = asyncio.create_task(self._run(), name="token-learning")

    def offer(
        self,
        *,
        request_id: str,
        attempt_index: int,
        body: bytes,
        actual_input_tokens: int,
        provider_name: str,
        resolved_model: str,
        endpoint: ModelEndpoint,
        target_format: WireFormat,
        descriptor: ModelDescriptor,
    ) -> bool:
        if self._state != "running":
            return False
        if target_format is not WireFormat.OPENAI_RESPONSES:
            return False
        if type(actual_input_tokens) is not int or actual_input_tokens < 0:
            return False
        if len(body) > self._max_body_bytes:
            return False
        if self._pending_body_bytes + len(body) > self._max_body_bytes:
            return False
        offer = TokenLearningOffer(
            request_id=request_id,
            attempt_index=attempt_index,
            body=bytes(body),
            actual_input_tokens=actual_input_tokens,
            provider_name=provider_name,
            resolved_model=resolved_model,
            endpoint=endpoint,
            target_format=target_format,
            descriptor=descriptor,
            observed_at_us=time.time_ns() // 1_000,
        )
        try:
            self._queue.put_nowait(offer)
        except asyncio.QueueFull:
            return False
        self._pending_body_bytes += len(body)
        return True

    async def flush(self) -> None:
        await self._queue.join()
        if self._anchor_tasks:
            await asyncio.gather(*tuple(self._anchor_tasks), return_exceptions=True)

    async def predict_responses(
        self,
        *,
        payload: Mapping[str, Any],
        provider_name: str,
        resolved_model: str,
        endpoint: ModelEndpoint,
        target_format: WireFormat,
        descriptor: ModelDescriptor,
    ) -> TokenPrediction | None:
        if (
            self._state != "running"
            or target_format is not WireFormat.OPENAI_RESPONSES
        ):
            return None
        features = await self._worker.analyze_responses(
            payload,
            capabilities=descriptor.tokenization_capabilities,
        )
        identity = LearningIdentity(
            actual_provider=provider_name,
            resolved_model=resolved_model,
            endpoint=endpoint.value,
            wire_format=target_format.value,
            tokenizer=TOKENIZER_NAME,
            descriptor_fingerprint=descriptor_fingerprint(descriptor),
            estimator_generation=features.estimator_generation,
            profile_schema_revision=features.profile_schema_revision,
            learning_epoch=0,
        )
        snapshot = await self._store.snapshot_for_prediction(identity)
        decision = predict_exact_or_prefix(features, snapshot)
        if decision.anchor_use_intent is not None:
            task = asyncio.create_task(
                self._record_anchor_use(decision.anchor_use_intent),
                name="token-learning-anchor-use",
            )
            self._anchor_tasks.add(task)
            task.add_done_callback(self._anchor_tasks.discard)
        return decision.prediction

    async def close(self) -> None:
        if self._state == "closed":
            return
        if self._state == "new":
            self._state = "closed"
            return
        self._state = "closing"
        await self._queue.put(None)
        if self._task is not None:
            await self._task
        await self.flush()
        await self._store.close()
        self._state = "closed"

    async def _run(self) -> None:
        while True:
            offer = await self._queue.get()
            if offer is None:
                self._queue.task_done()
                return
            self._pending_body_bytes -= len(offer.body)
            try:
                await self._learn(offer)
            except Exception:
                logger.exception(
                    "token learning offer failed: provider=%s model=%s attempt=%d",
                    offer.provider_name,
                    offer.resolved_model,
                    offer.attempt_index,
                )
            finally:
                self._queue.task_done()

    async def _record_anchor_use(self, intent: Any) -> None:
        try:
            await self._store.record_anchor_use(intent)
        except Exception:
            logger.exception("token learning anchor use failed")

    async def _learn(self, offer: TokenLearningOffer) -> None:
        decoded = loads(offer.body)
        if not isinstance(decoded, Mapping):
            raise ValueError("actual Responses request body is not an object")
        payload = cast(Mapping[str, Any], decoded)
        features = await self._worker.analyze_responses(
            payload,
            capabilities=offer.descriptor.tokenization_capabilities,
        )
        raw_body_sha256 = hashlib.sha256(offer.body).hexdigest()
        features = replace(features, raw_sent_body_sha256=raw_body_sha256)
        identity = LearningIdentity(
            actual_provider=offer.provider_name,
            resolved_model=offer.resolved_model,
            endpoint=offer.endpoint.value,
            wire_format=offer.target_format.value,
            tokenizer=TOKENIZER_NAME,
            descriptor_fingerprint=descriptor_fingerprint(offer.descriptor),
            estimator_generation=features.estimator_generation,
            profile_schema_revision=features.profile_schema_revision,
            learning_epoch=0,
        )
        sample_key = (_PROCESS_BOOT_ID, offer.request_id, offer.attempt_index)
        analyzed_sample = StoredSample(
            sample_key=sample_key,
            identity=identity,
            features=features,
            actual_input_tokens=offer.actual_input_tokens,
            raw_body_sha256=raw_body_sha256,
            observed_at_us=offer.observed_at_us,
        )

        def transition(snapshot: LearningSnapshot) -> LearningUpdate:
            sample = replace(analyzed_sample, identity=snapshot.identity)
            record = build_prediction_record(sample_key, features, snapshot)
            evaluations = evaluate(record, offer.actual_input_tokens)
            return LearningUpdate(
                sample=sample,
                prediction_record=record,
                evaluations=evaluations,
                prefix_checkpoint_command=NoPrefixCheckpointChange(),
            )

        result = await self._store.apply_sample(analyzed_sample, transition)
        logger.debug(
            "token learning sample %s: %s",
            result.observation.sample_key,
            result.observation.outcome,
        )
