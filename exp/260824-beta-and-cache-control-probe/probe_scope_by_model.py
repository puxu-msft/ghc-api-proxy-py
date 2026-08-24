"""Is `cache_control.scope` refused by every model, or only by some?

The question decides the shape of the repair. If some models take it, removing it unconditionally costs those models a cache scope the client asked for, and the strip belongs on a per-model table like `strip_anthropic_beta_flags`. If none do, a single rule is right.

The refusal measured on `claude-opus-5` came back in Anthropic's own envelope (`invalid_request_error`) rather than the gateway's, which is what makes "per model" a live possibility at all: the gateway's vocabulary is deployment-wide, but a body schema is served behind whichever model answers.

Every model gets a positive control in the same run — the same body without `scope`. A 400 on a model whose control also fails says nothing about `scope`.
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

MODELS = [
    "claude-opus-5",
    "claude-opus-4.8",
    "claude-opus-4.7",
    "claude-opus-4.6",
    "claude-sonnet-5",
    "claude-sonnet-4.6",
    "claude-haiku-4.5",
]


def body(model: str, marker: dict[str, Any] | None) -> dict[str, Any]:
    second: dict[str, Any] = {"type": "text", "text": "Be concise."}
    if marker is not None:
        second["cache_control"] = marker
    return {
        "model": model,
        "max_tokens": 16,
        "system": [{"type": "text", "text": "You are a helpful assistant."}, second],
        "messages": [{"role": "user", "content": "Say OK."}],
    }


async def run() -> None:
    config = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=120.0) as client:
        gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
        h = {**build_identity_headers(config), "Accept": "application/json", "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await client.get(AUTH_URL, headers=h)
        r.raise_for_status()
        token, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")

        print(f"{'model':20} {'control':>8} {'scope':>8} {'ttl=1h':>8}  note")
        for model in MODELS:
            row: dict[str, Any] = {}
            for label, marker in (
                ("control", None),
                ("scope", {"type": "ephemeral", "scope": "organization"}),
                ("ttl", {"type": "ephemeral", "ttl": "1h"}),
            ):
                headers = build_request_headers(token, config, interaction_id=str(uuid4()))
                resp = await client.post(f"{base}/v1/messages", headers=headers, json=body(model, marker))
                note = ""
                if resp.status_code != 200:
                    try:
                        note = json.loads(resp.text).get("error", {}).get("message", "")[:110]
                    except Exception:
                        note = resp.text[:110]
                row[label] = (resp.status_code, note)
            notes = {v[1] for v in row.values() if v[1]}
            print(
                f"{model:20} {row['control'][0]:>8} {row['scope'][0]:>8} {row['ttl'][0]:>8}  "
                + (" | ".join(sorted(notes)) if notes else "")
            )


asyncio.run(run())
