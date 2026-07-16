from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.observability.telemetry import RequestTelemetry, setup_metrics
from app.observability.tracing import setup_tracing, trace_context
from app.server import create_app


def test_tracing_default_off_and_opt_in_idempotent() -> None:
    app = FastAPI()
    assert setup_tracing(app, enabled=False) is False
    first = setup_tracing(app, enabled=True)
    second = setup_tracing(app, enabled=True)
    assert first is True
    assert second is False


def test_trace_context_is_empty_without_active_span() -> None:
    assert trace_context() == {}


def test_otel_telemetry_records_without_handwritten_counter_state() -> None:
    setup_metrics()
    telemetry = RequestTelemetry()
    telemetry.record_request(
        model="test",
        endpoint="anthropic-messages",
        status="success",
        duration_ms=10,
        input_tokens=2,
        output_tokens=3,
        reasoning_tokens=1,
    )
    assert not hasattr(telemetry, "_counters")


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    setup_metrics()
    RequestTelemetry().record_request(
        model="visible-model",
        endpoint="test-endpoint",
        status="success",
        duration_ms=1,
        input_tokens=1,
        output_tokens=1,
        reasoning_tokens=0,
    )
    with TestClient(create_app(AppSettings())) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "ghc_proxy_requests" in response.text
    assert "visible-model" in response.text