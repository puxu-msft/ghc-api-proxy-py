"""What the Responses endpoint does with the tool fields the Anthropic translation forwards.

The third 400 a user reported, on the translated leg this time:

    Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.

`translation_driver/openai_responses.py`'s `_function_tool` copies every key except `input_schema`, so anything Anthropic puts on a tool travels to an endpoint that never agreed to it. `defer_loading` is the one that was reported; `cache_control` rides the same line and has never been measured here, which is why it is in this matrix too.

P0 is the positive control. A row of 400s could equally mean the model name or the body shape is wrong.

The tool_search cases are guesses at a shape upstream named but did not spell. They are here to find out whether a mapping is even available — not to build one.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

TOKEN_FILE = Path.home() / ".local/share/ghc-api-proxy/github_token"
AUTH_URL = "https://api.github.com/copilot_internal/v2/token"
MODEL = "gpt-5.6-sol"

WEATHER: dict[str, Any] = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the weather.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
}
CLOCK: dict[str, Any] = {
    "type": "function",
    "name": "get_time",
    "description": "Get the time.",
    "parameters": {"type": "object", "properties": {}},
}


def body(tools: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Say OK."}]}],
        "max_output_tokens": 32,
        "stream": False,
    }
    if tools is not None:
        payload["tools"] = tools
    payload.update(extra)
    return payload


CASES: list[dict[str, Any]] = [
    {"name": "P0-control-plain-function-tools", "body": body([WEATHER, CLOCK])},
    {
        "name": "P1-defer-loading-as-translated-today",
        "why": "Reproduces the reported 400: what `_function_tool` forwards when Claude Code marks a tool deferred.",
        "body": body([{**WEATHER, "defer_loading": True}, CLOCK]),
    },
    {
        "name": "P2-defer-loading-false-only",
        "why": "Whether the key itself is refused or only a true value. Decides whether a strip may keep an explicit false.",
        "body": body([{**WEATHER, "defer_loading": False}, CLOCK]),
    },
    {
        "name": "P3-cache-control-on-a-tool",
        "why": "The same forwarding line carries this one. Never measured on this leg; if it is refused, it is a second latent 400 in the same place.",
        "body": body([{**WEATHER, "cache_control": {"type": "ephemeral"}}, CLOCK]),
    },
    {
        "name": "P4-cache-control-with-scope-on-a-tool",
        "why": "And the scope variant, since the Anthropic leg refuses that one specifically.",
        "body": body([{**WEATHER, "cache_control": {"type": "ephemeral", "scope": "organization"}}, CLOCK]),
    },
    {
        "name": "P5-anthropic-tool-search-server-tool",
        "why": "What happens if Anthropic's hosted tool-search declaration reaches this endpoint unchanged.",
        "body": body([{"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}, WEATHER]),
    },
    {
        "name": "P6-defer-loading-with-tool-search-builtin",
        "why": "The shape upstream's own message points at: a `tool_search` tool beside the deferred ones. A guess at the spelling.",
        "body": body([{"type": "tool_search"}, {**WEATHER, "defer_loading": True}, CLOCK]),
    },
    {
        "name": "P7-defer-loading-with-top-level-tool-search",
        "why": "The other reading of 'tools.tool_search': a field rather than a tool.",
        "body": body([{**WEATHER, "defer_loading": True}, CLOCK], tool_search=True),
    },
]


async def run() -> None:
    config = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=120.0) as client:
        gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
        h = {**build_identity_headers(config), "Accept": "application/json", "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await client.get(AUTH_URL, headers=h)
        r.raise_for_status()
        token, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")

        for case in CASES:
            headers = build_request_headers(token, config, interaction_id=str(uuid4()))
            resp = await client.post(f"{base}/responses", headers=headers, json=case["body"])
            msg = ""
            if resp.status_code != 200:
                try:
                    msg = json.loads(resp.text).get("error", {}).get("message", resp.text[:300])
                except Exception:
                    msg = resp.text[:300]
            print(f"[{'OK ' if resp.status_code == 200 else resp.status_code}] {case['name']}: {msg}")


asyncio.run(run())
