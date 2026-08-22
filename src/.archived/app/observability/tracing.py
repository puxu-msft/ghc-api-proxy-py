# pyright: reportMissingTypeStubs=false

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import (
    FastAPIInstrumentor,
)
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
)


def setup_tracing(app: FastAPI, *, enabled: bool) -> bool:
    if not enabled or getattr(app.state, "otel_instrumented", False):
        return False
    FastAPIInstrumentor.instrument_app(app)
    # `HTTPX2ClientInstrumentor`, not `HTTPXClientInstrumentor`: the two are separate classes over the same package, each patching the transport of the module it is named for. The old one still imports and still instruments cleanly here — it would simply be patching a package nothing in this process uses, and every outbound span would disappear without a word.
    if not HTTPX2ClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPX2ClientInstrumentor().instrument()
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
