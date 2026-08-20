"""Record the two web-search cassettes from the real upstream.

    PYTHONPATH=src:tests/integration uv run python exp/260820-websearch-probe/record.py

Why not a scenario in `tests/integration/recorded/record_cassette.py`: that entry drives a whole chain from `/v1/messages` through `handle_bounded`, and today the Responses leg does not emit any `web_search` tool — `builtin:server-tool-capability` strips the Anthropic declaration and nothing maps it onward. So the request that produces a `web_search_call` cannot be made by the product code yet. This recorder posts the Responses body directly instead, through the same `RecordingTransport`, so the cassette on disk is in the ordinary format with the ordinary scrubbing and the wire's own chunk boundaries. Move it into a scenario once the mapping exists.

The token exchange is recorded too, so a replay runs the real token manager against a recorded answer, exactly as the other cassettes do.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from recorded.cassettes import RecordingTransport

from app.ghc_client.config import GhcClientConfig
from app.ghc_client.headers import build_identity_headers, build_request_headers

CASSETTE_DIR = Path(__file__).resolve().parents[2] / "tests" / "cassettes"
TOKEN_FILE = Path.home() / ".local/share/copilot-api/github_token"
BASE_URL = "https://api.githubcopilot.com"
AUTH_URL = "https://api.github.com/copilot_internal/v2/token"

PROMPT = "Search the web for today's date."

SCENARIOS: dict[str, dict[str, Any]] = {
    "responses_web_search_nonstream": {
        "model": "gpt-5.5",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": PROMPT}]}],
        "max_output_tokens": 512,
        "stream": False,
        "tools": [{"type": "web_search"}],
    },
    "responses_web_search_stream": {
        "model": "gpt-5.5",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": PROMPT}]}],
        "max_output_tokens": 512,
        "stream": True,
        "tools": [{"type": "web_search"}],
    },
}


async def record(name: str) -> None:
    body = SCENARIOS[name]
    config = GhcClientConfig()
    recorder = RecordingTransport()
    client = httpx.AsyncClient(transport=recorder, timeout=180)
    try:
        gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
        exchange = await client.get(
            AUTH_URL,
            headers={
                **build_identity_headers(config),
                "Accept": "application/json",
                "Authorization": f"token {gh}",
                "X-GitHub-Api-Version": "2025-04-01",
            },
        )
        exchange.raise_for_status()
        token = str(exchange.json()["token"])

        headers = build_request_headers(token, config, interaction_id="cassette")
        if body["stream"]:
            headers["accept"] = "text/event-stream"
        async with client.stream(
            "POST", f"{BASE_URL}/responses", headers=headers, json=body
        ) as response:
            async for _ in response.aiter_raw():
                pass
    finally:
        await client.aclose()

    destination = CASSETTE_DIR / f"{name}.json"
    recorder.cassette.write(destination)
    print(f"wrote {destination} ({len(recorder.cassette.interactions)} interactions)")
    for interaction in recorder.cassette.interactions:
        print(
            f"  {interaction.method:5} {interaction.path:36} "
            f"status={interaction.status} chunks={len(interaction.chunks)}"
        )


def main() -> int:
    names = sys.argv[1:] or list(SCENARIOS)
    for name in names:
        if name not in SCENARIOS:
            print(f"unknown scenario {name}", file=sys.stderr)
            return 2
    asyncio.run(_record_all(names))
    return 0


async def _record_all(names: list[str]) -> None:
    for name in names:
        await record(name)


if __name__ == "__main__":
    raise SystemExit(main())
