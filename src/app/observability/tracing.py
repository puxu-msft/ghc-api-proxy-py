# pyright: reportMissingTypeStubs=false

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import (
    FastAPIInstrumentor,
)
from opentelemetry.instrumentation.httpx import (
    HTTPXClientInstrumentor,
)


def setup_tracing(app: FastAPI, *, enabled: bool) -> bool:
    if not enabled or getattr(app.state, "otel_instrumented", False):
        return False
    FastAPIInstrumentor.instrument_app(app)
    if not HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().instrument()
    app.state.otel_instrumented = True
    return True


def trace_context() -> dict[str, str]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
    }