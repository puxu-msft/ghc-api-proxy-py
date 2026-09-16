"""Minimal mock upstream SSE server for the PoC.

Emits a handful of SSE `data: {...}` chunks with artificial delays between them,
so we can prove whether the openai SDK's low-level `client.post(...)` path
delivers bytes as they arrive (no internal buffering) or only after the whole
response body has been read.

Also echoes back the headers it received (in a special first SSE event) so we
can confirm custom Copilot-style headers survive the SDK's request pipeline.
"""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn

app = FastAPI()

CHUNK_DELAY_SECONDS = 0.4
NUM_CHUNKS = 5


async def sse_event_stream(received_headers: dict[str, str], received_body: dict):
    # First event: echo back what the server actually received, so the client
    # side can assert header / extra-body pass-through without a shared mutable
    # variable across the ASGI boundary.
    echo_payload = {
        "type": "echo",
        "headers": received_headers,
        "body": received_body,
    }
    yield f"data: {json.dumps(echo_payload)}\n\n".encode()

    for i in range(NUM_CHUNKS):
        # Deliberately sleep BETWEEN chunks (not before the first) so a
        # client-side "time of first byte" vs "time of last byte" comparison
        # is meaningful.
        await asyncio.sleep(CHUNK_DELAY_SECONDS)
        payload = {
            "type": "chunk",
            "index": i,
            "choices": [{"delta": {"content": f"tok-{i}"}}],
        }
        yield f"data: {json.dumps(payload)}\n\n".encode()

    yield b"data: [DONE]\n\n"


@app.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    # Interesting headers we want to confirm survive SDK -> httpx -> ASGI.
    interesting = [
        "authorization",
        "copilot-integration-id",
        "editor-version",
        "x-initiator",
        "openai-intent",
        "user-agent",
    ]
    received_headers = {h: request.headers.get(h) for h in interesting}
    return StreamingResponse(
        sse_event_stream(received_headers, body),
        media_type="text/event-stream",
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8811, log_level="warning")
