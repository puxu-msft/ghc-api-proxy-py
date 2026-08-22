"""Record a cassette from the real upstream.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src:tests/int uv run python \\
        tests/int/recorded/record_cassette.py anthropic_to_responses_stream

The prompts are deliberately trivial ("Reply with exactly: PONG") because a cassette is committed and read by people. Nothing here should ever carry a real conversation.

Secrets are removed on the way to disk, not on the way through: the live code below this transport must receive what upstream actually sent. Handing it a redacted token once made it authenticate with the literal word REDACTED, and upstream said so.

The config is pinned rather than loaded. Recording once used `load_proxy_config()` and picked up whichever `model_mappings` happened to be on the machine, so `gpt-5.5` went out as `gpt-5.6-terra` while the replay — which pins its own config — still asked for `gpt-5.5`, and the shape guard fired on a cassette that had just been recorded. Only credentials may come from the environment.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.pipeline.driver import handle_bounded
from app.server.composition import build_chain, refresh_catalogs
from app.server.inbound import build_context
from app.server.routes.table import route_for_path
from recorded.cassettes import RecordingTransport
from recorded.recorded_provider import pinned_config

# Data, not code: cassettes stay under `tests/` so they are easy to find and diff, while the harness lives with the one group that imports it.
CASSETTE_DIR = Path(__file__).resolve().parents[1] / "cassettes"

# Each scenario is one recorded session: whatever requests it makes, in the order it makes them.
SCENARIOS: dict[str, dict[str, Any]] = {
    "anthropic_to_responses_stream": {
        "model": "gpt-5.5",
        "max_tokens": 64,
        "stream": True,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    },
}


async def record(name: str) -> None:
    body = SCENARIOS[name]
    config: ProxyConfig = pinned_config()
    recorder = RecordingTransport()
    client = httpx2.AsyncClient(transport=recorder, timeout=120)
    try:
        chain = build_chain(config, http_client=client)
        await refresh_catalogs(chain)
        route = route_for_path("/v1/messages")
        if route is None:
            raise RuntimeError("no route for /v1/messages")
        handled = await handle_bounded(chain, build_context(route, body))
        response = handled.response
        if response is None:
            raise RuntimeError(f"scenario {name} produced no response")
        # Drained so the streamed chunks reach the recorder; the content itself is not the point.
        async for _ in response.aiter_bytes():
            pass
    finally:
        await client.aclose()

    destination = CASSETTE_DIR / f"{name}.json"
    recorder.cassette.write(destination)
    print(f"wrote {destination} ({len(recorder.cassette.interactions)} interactions)")
    for interaction in recorder.cassette.interactions:
        print(
            f"  {interaction.method:5} {interaction.path:34} "
            f"status={interaction.status} chunks={len(interaction.chunks)}"
        )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        print(f"usage: record_cassette.py {{{'|'.join(SCENARIOS)}}}", file=sys.stderr)
        return 2
    asyncio.run(record(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
