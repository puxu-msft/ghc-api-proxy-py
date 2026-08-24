"""The repair on the real chain, against the real upstream.

Unit tests prove the subscriber does the right thing; this proves the config
reaches it and the body that leaves is the one upstream accepts. Three cases,
each a real call:

  1. default (`passthrough`)      -> must still 400. That is the ruling.
  2. `cache_control: sanitize`    -> must 200.
  3. sanitize + the refused beta  -> must 200; the gateway strip is unconditional.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.driver import handle
from app.server.composition import build_chain, build_copilot_provider, refresh_catalogs

SCOPE = {"type": "ephemeral", "scope": "organization"}


def body() -> dict[str, Any]:
    return {
        "model": "claude-opus-4.6",
        "max_tokens": 16,
        "system": [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise.", "cache_control": dict(SCOPE)},
        ],
        "messages": [{"role": "user", "content": "Say OK."}],
    }


async def run_case(label: str, mode: str, beta: str | None) -> None:
    raw: dict[str, Any] = {
        "default_model_provider": "ghc",
        "model_providers": {"ghc": {"type": "github_copilot"}},
        "model_mappings": {"opus": "claude-opus-4.6"},
    }
    if mode != "default":
        raw["hook_fix_anthropic_request"] = {"cache_control": mode}
    config = ProxyConfig.model_validate(raw)
    async with httpx2.AsyncClient(timeout=120.0) as client:
        chain = build_chain(config, http_client=client)
        await refresh_catalogs(chain)
        headers = {"anthropic-beta": beta} if beta else {}
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="claude-opus-4.6",
            payload=body(),
            client_headers=headers,
        )
        try:
            result = await handle(chain, context)
        except Exception as exc:  # noqa: BLE001 - a refusal raised is still a result
            print(f"[400 ] {label}: raised {type(exc).__name__}: {str(exc)[:170]}")
            return
        outcome = result.outcome
        # `succeeded` is the real predicate: a refusal rides in `outcome.error`, it is not raised.
        if outcome.succeeded and outcome.response is not None:
            print(f"[ 200] {label}: HTTP {outcome.response.status_code}")
        else:
            print(f"[400 ] {label}: {type(outcome.error).__name__}: {str(outcome.error)[:170]}")


async def main() -> None:
    await run_case("1 default passthrough + scope (must FAIL, that is the ruling)", "default", None)
    await run_case("2 sanitize + scope (must be OK)", "sanitize", None)
    await run_case("3 sanitize + scope + refused beta (must be OK)", "sanitize",
                   "claude-code-20250219,tool-search-tool-2025-10-19")


asyncio.run(main())
