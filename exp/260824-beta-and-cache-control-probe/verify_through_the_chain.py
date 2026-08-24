"""The repair on the real chain, against the real upstream.

Unit tests prove the subscriber does the right thing; this proves the config
reaches it and the body that leaves is the one upstream accepts. Three cases,
each a real call:

  1. shipped config, nothing set  -> must 200. `sanitize` is the default and
                                     `bundled-config.yaml` names `scope` for Claude.
  2. explicit `passthrough`       -> must 400. That mode is literal, by ruling,
                                     and this is the case that proves the probe
                                     can fail at all.
  3. shipped config + refused beta -> must 200; the gateway strip is unconditional.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.driver import handle
from app.config.loading import bundled_config_values
from app.server.composition import build_chain, refresh_catalogs

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
    # Layered on the real shipped values, so this exercises what an operator gets rather than what a hand-built config happens to say.
    raw: dict[str, Any] = {
        **bundled_config_values(),
        "default_model_provider": "ghc",
        "model_providers": {"ghc": {"type": "github_copilot"}},
        "model_mappings": {"opus": "claude-opus-4.6"},
    }
    if mode != "shipped":
        hook = dict(raw.get("hook_fix_anthropic_request") or {})
        hook["cache_control"] = mode
        raw["hook_fix_anthropic_request"] = hook
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
    await run_case("1 shipped config + scope (must be OK, out of the box)", "shipped", None)
    await run_case("2 explicit passthrough + scope (must FAIL, the mode is literal)", "passthrough", None)
    await run_case("3 shipped config + scope + refused beta (must be OK)", "shipped",
                   "claude-code-20250219,tool-search-tool-2025-10-19")


asyncio.run(main())
