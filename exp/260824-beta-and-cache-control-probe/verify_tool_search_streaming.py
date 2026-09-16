"""The tool-search translation over the served path, streaming, against the real upstream.

The earlier verification called the two translation functions directly and set
`stream=False`. A review pointed out what that leaves unproven: the chain that
carries the search tool's name from the request half to the response half is
never exercised, and the streaming assembler -- the path production uses -- had
never run against the real endpoint at all.

So this one goes through `handle()` and the real assembler, with `stream: True`,
and prints the Anthropic blocks a client would receive.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any

import httpx2

from app.config.loading import bundled_config_values
from app.config.schema import ProxyConfig
from app.pipeline.delivery_policy import assembler_for
from app.pipeline.driver import CLIENT_SEARCH_TOOL, handle
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.delivery.sse_source import read_events
from app.server.composition import build_chain, refresh_catalogs

SEARCH = {"name": "ToolSearch",
          "description": "Fetches full schema definitions for deferred tools so they can be called.",
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}
DEFERRED = {"name": "get_weather", "description": "Get the current weather for a city.",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "defer_loading": True}


async def run() -> None:
    config = ProxyConfig.model_validate({
        **bundled_config_values(),
        "default_model_provider": "ghc",
        "model_providers": {"ghc": {"type": "github_copilot"}},
        "model_mappings": {"gpt": "gpt-5.6-sol"},
    })
    async with httpx2.AsyncClient(timeout=180.0) as client:
        chain = build_chain(config, http_client=client)
        await refresh_catalogs(chain)
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="gpt",
            payload={
                "model": "gpt", "max_tokens": 400, "stream": True,
                "tools": [SEARCH, DEFERRED],
                "messages": [{"role": "user", "content": "What is the weather in Paris? Use a tool."}],
            },
        )
        handled = await handle(chain, context)
        name = context.extras.get(CLIENT_SEARCH_TOOL, "")
        print(f"name carried on the context: {name!r}")

        outcome = handled.outcome
        if not outcome.succeeded or outcome.response is None:
            print(f"[FAIL] {type(outcome.error).__name__}: {str(outcome.error)[:180]}")
            return

        assembler = assembler_for(handled)
        print(f"assembler built with: {getattr(assembler, '_client_search_tool', None)!r}")
        blocks: list[Any] = []
        async for event in read_events(outcome.response.aiter_bytes()):
            blocks.extend(assembler.push(event))
        rendered = [
            f"{b.payload.get('type')}:{b.payload.get('name')}"
            if b.payload.get("type") == "tool_use" else str(b.payload.get("type"))
            for b in blocks
        ]
        print(f"[ 200] streamed blocks the client would receive: {' | '.join(rendered) or '(none)'}")
        for b in blocks:
            if b.payload.get("type") == "tool_use":
                print(f"        input={b.payload.get('input')}")


asyncio.run(run())
