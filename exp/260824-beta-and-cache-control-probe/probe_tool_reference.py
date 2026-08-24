"""The second round of a custom tool search, with the beta removed.

The gap the beta investigation left open, and the one that decides whether the repair may be a plain strip. Claude Code 2.1.241 does not send Anthropic's hosted `tool_search_tool_regex_*`; it declares an ordinary client-executed `ToolSearch` tool, marks the candidates `defer_loading: true`, and on the **next** turn sends the search result back as `tool_result.content[]` blocks of `{"type": "tool_reference", "tool_name": …}`.

The first round was already measured as accepted without the beta. This measures the second, because that is where a `tool_reference` block appears — and a block upstream does not recognise is the exact shape `request_headers.py:11` warns about: the beta is gone, so the field it enabled becomes an unrecognised field and the request dies. If that happens here, stripping the flag only moves the failure to whichever turn the model first calls ToolSearch.

R0 is the positive control: the same two-round conversation with an ordinary text `tool_result` instead of a `tool_reference`. If it is not 200, nothing below is a verdict on `tool_reference`.
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
MODEL = "claude-opus-5"

SEARCH_TOOL: dict[str, Any] = {
    "name": "ToolSearch",
    "description": "Search for available tools by a regex pattern.",
    "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
}
DEFERRED_TOOL: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    "defer_loading": True,
}

def conversation(result_content: Any) -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "What tools can get the weather?"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "ToolSearch", "input": {"pattern": "weather"}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": result_content}],
        },
    ]

def body(result_content: Any) -> dict[str, Any]:
    return {
        "model": MODEL,
        "max_tokens": 32,
        "tools": [SEARCH_TOOL, DEFERRED_TOOL],
        "messages": conversation(result_content),
    }

TOOL_REFERENCE = [{"type": "tool_reference", "tool_name": "get_weather"}]

CASES: list[dict[str, Any]] = [
    {
        "name": "R0-control-plain-text-result",
        "why": "Positive control: same two-round shape, ordinary text result.",
        "body": body("Found: get_weather"),
    },
    {
        "name": "R1-tool-reference-no-beta",
        "why": "THE question. The second round as Claude Code sends it, with the flag stripped.",
        "body": body(TOOL_REFERENCE),
    },
    {
        "name": "R2-tool-reference-with-1119-beta",
        "why": "Same body under the beta the gateway does accept. Separates 'the block is unknown' from 'the block needs a beta we can still send'.",
        "beta": "tool-search-tool-2025-11-19",
        "body": body(TOOL_REFERENCE),
    },
    {
        "name": "R3-tool-reference-with-advanced-tool-use",
        "why": "The other accepted flag in the same family, in case that is the one carrying it.",
        "beta": "advanced-tool-use-2025-11-20",
        "body": body(TOOL_REFERENCE),
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
            if case.get("beta"):
                headers["anthropic-beta"] = case["beta"]
            resp = await client.post(f"{base}/v1/messages", headers=headers, json=case["body"])
            msg = ""
            if resp.status_code != 200:
                try:
                    msg = json.loads(resp.text).get("error", {}).get("message", resp.text[:300])
                except Exception:
                    msg = resp.text[:300]
            print(f"[{'OK ' if resp.status_code == 200 else resp.status_code}] {case['name']}: {msg}")

asyncio.run(run())
