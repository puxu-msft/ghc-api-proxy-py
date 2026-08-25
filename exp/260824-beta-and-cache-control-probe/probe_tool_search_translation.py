"""What the Responses endpoint does with `tool_search`, and who executes the search.

The user ruled that a client sending tool search should have it *translated*, not
stripped. Whether that is possible turns on a question a status code cannot answer:
Responses' `ToolSearchToolParam` carries `execution: "server" | "client"`, so the wire
can express both, but the translation is only right if the model then behaves the way
the Anthropic side's client expects.

So each case prints the **output item types** the model actually produced, not just
whether the request was accepted. The prompt asks for something only a deferred tool
can answer, so a model that never searches cannot answer it.
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

DEFERRED = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    "defer_loading": True,
}
ANCHOR = {
    "type": "function",
    "name": "ping",
    "description": "Health check.",
    "parameters": {"type": "object", "properties": {}},
    "defer_loading": False,
}
CLIENT_SEARCH_SHAPE = {
    "type": "tool_search",
    "execution": "client",
    "description": "Search for available tools by a regex pattern.",
    "parameters": {
        "type": "object",
        "properties": {"pattern": {"type": "string"}},
        "required": ["pattern"],
    },
}


def body(tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "What is the weather in Paris? Use a tool."}],
            }
        ],
        "tools": tools,
        "max_output_tokens": 400,
        "stream": False,
    }


CASES: list[dict[str, Any]] = [
    {"name": "S0-control-no-defer-no-search", "tools": [dict(ANCHOR), {**DEFERRED, "defer_loading": False}]},
    {"name": "S1-server-execution", "tools": [{"type": "tool_search", "execution": "server"}, DEFERRED, ANCHOR]},
    {"name": "S2-client-execution-full", "tools": [CLIENT_SEARCH_SHAPE, DEFERRED, ANCHOR]},
    {"name": "S3-client-execution-bare", "tools": [{"type": "tool_search", "execution": "client"}, DEFERRED, ANCHOR]},
    {"name": "S4-no-execution-field", "tools": [{"type": "tool_search"}, DEFERRED, ANCHOR]},
]


async def run() -> None:
    config = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=180.0) as client:
        gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
        h = {**build_identity_headers(config), "Accept": "application/json", "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await client.get(AUTH_URL, headers=h)
        r.raise_for_status()
        token, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")

        for case in CASES:
            headers = build_request_headers(token, config, interaction_id=str(uuid4()))
            resp = await client.post(f"{base}/responses", headers=headers, json=body(case["tools"]))
            if resp.status_code != 200:
                try:
                    msg = json.loads(resp.text).get("error", {}).get("message", resp.text[:200])
                except Exception:
                    msg = resp.text[:200]
                print(f"[{resp.status_code}] {case['name']}: {msg}")
                continue
            payload = resp.json()
            items = payload.get("output") or []
            summary: list[str] = []
            for item in items:
                kind = item.get("type", "?")
                if kind in ("function_call", "custom_tool_call"):
                    summary.append(f"{kind}:{item.get('name')}")
                elif "tool_search" in kind:
                    summary.append(f"{kind}:{json.dumps(item.get('action') or item.get('query') or '')[:60]}")
                else:
                    summary.append(kind)
            print(f"[ 200] {case['name']}: {' | '.join(summary) or '(no items)'}")


asyncio.run(run())
