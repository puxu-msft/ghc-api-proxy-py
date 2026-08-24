import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, cast

from app.errors import prompt_limit_counts
from app.transform.model_resolver import normalize_for_matching


def _error_message(raw: str) -> str:
    try:
        value: object = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(value, dict):
        return raw
    error = cast(dict[str, Any], value).get("error")
    if not isinstance(error, dict):
        return raw
    message = cast(dict[str, Any], error).get("message")
    return message if isinstance(message, str) else raw


def parse_prompt_limit_error(raw: str) -> tuple[int, int] | None:
    """The counts in an upstream error body, for learning what a model's real limit is.

    The patterns themselves live in `app.errors` beside the rest of the error vocabulary, because the error classifier recognises the same condition by the same wordings — see `.dev/docs/error-envelope/spec.md` §5.5.1. This end adds only the unwrapping: it is handed a whole body rather than a message.
    """
    return prompt_limit_counts(_error_message(raw))


@dataclass(slots=True)
class PromptLimitObservation:
    protocol: str
    model: str
    observed_limit: int
    observed_input_tokens: int
    source: str
    observed_at: float
    observation_count: int = 1


class PromptLimitRegistry:
    def __init__(self, *, on_change: Callable[[], None] | None = None) -> None:
        self._observations: dict[tuple[str, str], PromptLimitObservation] = {}
        self._on_change = on_change

    @staticmethod
    def _key(protocol: str, model: str) -> tuple[str, str]:
        return protocol.lower(), normalize_for_matching(model)

    def record(
        self,
        protocol: str,
        model: str,
        *,
        current: int,
        limit: int,
        source: str,
        observed_at: float | None = None,
    ) -> bool:
        if current <= limit or limit <= 0:
            return False
        key = self._key(protocol, model)
        existing = self._observations.get(key)
        self._observations[key] = PromptLimitObservation(
            protocol=key[0],
            model=key[1],
            observed_limit=limit,
            observed_input_tokens=current,
            source=source,
            observed_at=time.time() if observed_at is None else observed_at,
            observation_count=(existing.observation_count + 1 if existing else 1),
        )
        if self._on_change is not None:
            self._on_change()
        return True

    def get(self, protocol: str, model: str) -> PromptLimitObservation | None:
        return self._observations.get(self._key(protocol, model))

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            f"{protocol}:{model}": asdict(observation)
            for (protocol, model), observation in sorted(self._observations.items())
        }

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any],
        *,
        on_change: Callable[[], None] | None = None,
    ) -> PromptLimitRegistry:
        registry = cls(on_change=on_change)
        for raw_value in snapshot.values():
            if not isinstance(raw_value, dict):
                continue
            value = cast(dict[str, Any], raw_value)
            try:
                observation = PromptLimitObservation(
                    protocol=str(value["protocol"]),
                    model=str(value["model"]),
                    observed_limit=int(value["observed_limit"]),
                    observed_input_tokens=int(value["observed_input_tokens"]),
                    source=str(value["source"]),
                    observed_at=float(value["observed_at"]),
                    observation_count=int(value.get("observation_count", 1)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if observation.observed_input_tokens <= observation.observed_limit:
                continue
            registry._observations[
                registry._key(observation.protocol, observation.model)
            ] = observation
        return registry
