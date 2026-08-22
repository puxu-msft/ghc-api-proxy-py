"""Does tracing still see outbound requests after the move to httpx2?

`opentelemetry-instrumentation-httpx` ships two instrumentors over the same package, one bound to the module name `httpx` and one to `httpx2`. The wrong one installs cleanly, reports itself as instrumented, and patches a package nothing in this process imports — every outbound span simply stops appearing, with no error and no log line. `tests/unit/test_imports.py` cannot see that: the module name it imports is the same either way.

So this asserts on exported spans, against a real loopback server, because the instrumentation patches `AsyncHTTPTransport.handle_async_request` and a mock transport never reaches it.
"""

from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx2
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.tracing import setup_tracing


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # The name is fixed by BaseHTTPRequestHandler.
        self.send_response(200)
        self.send_header("content-length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        del format, args  # The suite's output is not a place for one line per probe request.


@pytest.fixture
def loopback_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/probe"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def exported_spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # The raw global, not `get_tracer_provider()`: that returns a proxy which reads this same global, so restoring it would point the global at something that resolves to itself.
    previous = trace._TRACER_PROVIDER  # pyright: ignore[reportPrivateUsage]
    trace._TRACER_PROVIDER = provider  # pyright: ignore[reportPrivateUsage]
    try:
        yield exporter
    finally:
        # Global state, so it goes back: the instrumentor patches the transport class itself, and a later test asking whether `setup_tracing` instruments would otherwise be answered by this one's leftovers.
        HTTPX2ClientInstrumentor().uninstrument()
        trace._TRACER_PROVIDER = previous  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_an_outbound_request_still_produces_a_span(
    loopback_server: str,
    exported_spans: InMemorySpanExporter,
) -> None:
    """The whole point of naming the instrumentor: instrument the package we actually send with.

    Swap `HTTPX2ClientInstrumentor` back to `HTTPXClientInstrumentor` in `app.observability.tracing` and this goes red — nothing else in the suite does.
    """
    app = FastAPI()
    assert setup_tracing(app, enabled=True) is True

    async with httpx2.AsyncClient() as client:
        response = await client.get(loopback_server)
    assert response.status_code == 200

    # `http.url` rather than `url.full`: this instrumentation still emits the pre-1.0 HTTP semantic conventions unless `OTEL_SEMCONV_STABILITY_OPT_IN` says otherwise, and nothing here opts in.
    urls = [span.attributes.get("http.url") for span in exported_spans.get_finished_spans() if span.attributes]
    assert loopback_server in urls, f"no span for the outbound request; saw {urls}"
