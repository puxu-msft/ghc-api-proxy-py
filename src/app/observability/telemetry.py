from opentelemetry import metrics


class RequestTelemetry:
    def __init__(self) -> None:
        meter = metrics.get_meter("ghc-api-proxy")
        self._requests = meter.create_counter("ghc_proxy_requests")
        self._tokens = meter.create_counter("ghc_proxy_tokens")
        self._duration = meter.create_histogram("ghc_proxy_duration_ms")

    def record_request(
        self,
        *,
        model: str,
        endpoint: str,
        status: str,
        duration_ms: float,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
    ) -> None:
        attributes = {"model": model, "endpoint": endpoint, "status": status}
        self._requests.add(1, attributes)
        self._duration.record(duration_ms, attributes)
        for token_type, value in (
            ("input", input_tokens),
            ("output", output_tokens),
            ("reasoning", reasoning_tokens),
        ):
            self._tokens.add(value, {**attributes, "token_type": token_type})