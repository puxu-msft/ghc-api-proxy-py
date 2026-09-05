from collections.abc import Callable

import pytest
from prometheus_client import CollectorRegistry

from app.models.anthropic import MessagesRequest
from app.observability.metrics import ResponsivenessMetrics
from app.tokenization import estimators


@pytest.mark.parametrize(("format_name", "expected", "estimate_seconds"), [("anthropic", 8, .4), ("responses", 6, .2)])
def test_estimator_times_lookup_and_estimation_separately(
    monkeypatch: pytest.MonkeyPatch, format_name: str, expected: int, estimate_seconds: float,
) -> None:
    now = [10.0]
    registry = CollectorRegistry()
    metrics = ResponsivenessMetrics(registry, clock=lambda: now[0])
    monkeypatch.setattr(estimators, "RESPONSIVENESS", metrics)

    class Encoding:
        def encode(self, text: str) -> list[int]:
            now[0] += .2
            return [1, 2]

    def lookup(name: str) -> Encoding:
        assert name == "o200k_base"
        now[0] += .3
        return Encoding()

    monkeypatch.setattr(estimators.tiktoken, "get_encoding", lookup)
    assert estimate_call(format_name)() == expected
    for phase, duration in (("lookup", .3), ("estimate", estimate_seconds)):
        labels = {"format": format_name, "phase": phase}
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_count", labels) == 1
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_sum", labels) == pytest.approx(duration)
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_max_seconds", labels) == pytest.approx(duration)
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_failures_total", labels) == 0


@pytest.mark.parametrize("format_name", ["anthropic", "responses"])
@pytest.mark.parametrize("failing_phase", ["lookup", "estimate"])
def test_estimator_failure_identity_is_preserved(
    monkeypatch: pytest.MonkeyPatch, format_name: str, failing_phase: str,
) -> None:
    registry = CollectorRegistry()
    metrics = ResponsivenessMetrics(registry)
    monkeypatch.setattr(estimators, "RESPONSIVENESS", metrics)
    error = ValueError("known tokenizer failure")

    class Encoding:
        def encode(self, text: str) -> list[int]:
            raise error

    def lookup(name: str) -> Encoding:
        if failing_phase == "lookup":
            raise error
        return Encoding()

    monkeypatch.setattr(estimators.tiktoken, "get_encoding", lookup)
    with pytest.raises(ValueError) as caught:
        estimate_call(format_name)()
    assert caught.value is error
    labels = {"format": format_name, "phase": failing_phase}
    assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_failures_total", labels) == 1
    assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_count", labels) == 1
    if failing_phase == "lookup":
        assert registry.get_sample_value("ghc_proxy_local_tokenizer_duration_seconds_count", {"format": format_name, "phase": "estimate"}) == 0


def estimate_call(format_name: str) -> Callable[[], int]:
    if format_name == "anthropic":
        request = MessagesRequest.model_validate({"model": "test", "max_tokens": 1, "messages": [{"role": "user", "content": "hello"}]})
        return lambda: estimators.estimate_anthropic_input(request)
    return lambda: estimators.estimate_responses_input({"input": [{"type": "message", "role": "user", "content": "hello"}]})
