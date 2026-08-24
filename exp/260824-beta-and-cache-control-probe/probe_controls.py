"""Two controls the first run left ambiguous.

T1 in the first run returned 400 `At least one tool must have defer_loading=false`, which is upstream *enforcing* the field's semantics rather than refusing to recognise it — my case had a single tool and deferred it. So `defer_loading` being accepted without its beta was only shown incidentally, inside T2, alongside a server tool. D-series shows it on its own, because "stripping the beta is safe" rests on it.

E-series sends the whole beta set Claude Code negotiates, minus the two the gateway refuses, to confirm the combination is accepted and not just each flag alone.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4
from pathlib import Path

import httpx2 as httpx

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

TOKEN_FILE = Path.home() / ".local/share/ghc-api-proxy/github_token"
AUTH_URL = "https://api.github.com/copilot_internal/v2/token"
MODEL = "claude-opus-5"

WEATHER: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
}
CLOCK: dict[str, Any] = {
    "name": "get_time",
    "description": "Get the time.",
    "input_schema": {"type": "object", "properties": {}},
}

ACCEPTED_SET = ",".join([
    "claude-code-20250219",
    "oauth-2025-04-20",
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
    "context-management-2025-06-27",
    "prompt-caching-2024-07-31",
    "prompt-caching-scope-2026-01-05",
])

def body(**extra: Any) -> dict[str, Any]:
    return {"model": MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": "Say OK."}], **extra}

CASES: list[dict[str, Any]] = [
    {"name": "D0-control-two-plain-tools", "body": body(tools=[WEATHER, CLOCK])},
    {
        "name": "D1-defer-loading-mixed-no-beta",
        "why": "The field on its own, with one tool not deferred so the semantic rule T1 tripped is satisfied. This is what makes stripping the beta safe.",
        "body": body(tools=[{**WEATHER, "defer_loading": True}, {**CLOCK, "defer_loading": False}]),
    },
    {
        "name": "D2-defer-loading-mixed-with-1019-beta",
        "why": "Same body, the flag the client sends. Isolates the header as the sole cause.",
        "beta": "tool-search-tool-2025-10-19",
        "body": body(tools=[{**WEATHER, "defer_loading": True}, {**CLOCK, "defer_loading": False}]),
    },
    {
        "name": "E1-accepted-beta-set-together",
        "why": "The whole negotiated set minus the two refused, sent as one header value.",
        "beta": ACCEPTED_SET,
        "body": body(),
    },
    {
        "name": "E2-accepted-set-plus-1019",
        "why": "The realistic client header. Confirms one bad flag kills a set that is otherwise fine, and that the gateway names only the bad one.",
        "beta": f"{ACCEPTED_SET},tool-search-tool-2025-10-19",
        "body": body(),
    },
    {
        "name": "E3-scope-value-session",
        "why": "A different scope value, in case the refusal is about the value rather than the key. Same error means the key is what is unknown.",
        "body": body(system=[{"type": "text", "text": "A."}, {"type": "text", "text": "B.", "cache_control": {"type": "ephemeral", "scope": "session"}}]),
    },
    {
        "name": "E4-ttl-and-scope-together",
        "why": "Whether a body carrying both loses only the scope. Decides whether the strip may keep ttl.",
        "body": body(system=[{"type": "text", "text": "A."}, {"type": "text", "text": "B.", "cache_control": {"type": "ephemeral", "ttl": "1h", "scope": "session"}}]),
    },
]

async def run() -> None:
    config = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=120.0) as client:
        gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
        h = {**build_identity_headers(config), "Accept": "application/json", "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await client.get(AUTH_URL, headers=h)
        r.raise_for_status()
        token = r.json()["token"]
        base = r.json()["endpoints"]["api"].rstrip("/")

        for case in CASES:
            headers = build_request_headers(token, config, interaction_id=str(uuid4()))
            if case.get("beta"):
                headers["anthropic-beta"] = case["beta"]
            resp = await client.post(f"{base}/v1/messages", headers=headers, json=case["body"])
            msg = ""
            if resp.status_code != 200:
                try:
                    msg = json.loads(resp.text).get("error", {}).get("message", resp.text[:200])
                except Exception:
                    msg = resp.text[:200]
            print(f"[{'OK ' if resp.status_code == 200 else resp.status_code}] {case['name']}: {msg}")

asyncio.run(run())
