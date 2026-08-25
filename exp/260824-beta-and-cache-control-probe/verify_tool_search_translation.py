"""The tool-search translation, both directions, against the real endpoint.

Unit tests pin the shapes; this checks the endpoint agrees and that what comes
back can be handed to the client as a call on its own tool.

Turn 1  the client's search tool is promoted; the model should ask for a search.
        The response is translated back and must name the client's tool.
Turn 2  the client's answer (tool_reference blocks) is translated into a
        tool_search_output; the model should then call the deferred tool.
"""
from __future__ import annotations
import asyncio, json
from pathlib import Path
from typing import Any
from uuid import uuid4
import httpx2 as httpx
from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.registry import default_registry
from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

TOKEN = Path.home() / ".local/share/ghc-api-proxy/github_token"
SEARCH = {"name": "ToolSearch",
          "description": "Fetches full schema definitions for deferred tools so they can be called.",
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}
DEFERRED = {"name": "get_weather", "description": "Get the current weather for a city.",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "defer_loading": True}

def anthropic(messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"model": "gpt-5.6-sol", "max_tokens": 400, "tools": [SEARCH, DEFERRED], "messages": messages}

async def run() -> None:
    cfg = GhcClientConfig(account_type="enterprise")
    reg = default_registry()
    async with httpx.AsyncClient(timeout=180.0) as c:
        gh = TOKEN.read_text().strip()
        h = {**build_identity_headers(cfg), "Accept": "application/json",
             "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await c.get("https://api.github.com/copilot_internal/v2/token", headers=h); r.raise_for_status()
        tok, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")
        post = lambda body: c.post(f"{base}/responses",
                                   headers=build_request_headers(tok, cfg, interaction_id=str(uuid4())),
                                   json=body)

        messages: list[dict[str, Any]] = [{"role": "user", "content": "What is the weather in Paris? Use a tool."}]
        request = anthropic(messages)
        body, semantic = reg.translate(request, source=WireFormat.ANTHROPIC_MESSAGES, target=WireFormat.OPENAI_RESPONSES)
        body["stream"] = False
        name = semantic.client_search_tool
        print(f"identified search tool: {name!r}")
        resp = await post(body)
        if resp.status_code != 200:
            print(f"[turn1 {resp.status_code}] {resp.text[:200]}"); return
        back, _ = reg.translate_response(resp.json(), source=WireFormat.OPENAI_RESPONSES,
                                         target=WireFormat.ANTHROPIC_MESSAGES, client_search_tool=name)
        blocks = [f"{b.get('type')}:{b.get('name')}" if b.get("type") == "tool_use" else str(b.get("type"))
                  for b in back.get("content", [])]
        print(f"[turn1 200] client would see: {' | '.join(blocks)}  stop_reason={back.get('stop_reason')}")

        call = next((b for b in back.get("content", []) if b.get("type") == "tool_use"), None)
        if call is None:
            print("        no tool_use handed back; second turn not attempted"); return

        # The client answers its own tool with tool_reference blocks, exactly as Claude Code does.
        messages.append({"role": "assistant", "content": [call]})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call["id"],
             "content": [{"type": "tool_reference", "tool_name": "get_weather"}]}]})
        body2, semantic2 = reg.translate(anthropic(messages), source=WireFormat.ANTHROPIC_MESSAGES,
                                         target=WireFormat.OPENAI_RESPONSES)
        body2["stream"] = False
        resp2 = await post(body2)
        if resp2.status_code != 200:
            print(f"[turn2 {resp2.status_code}] {resp2.text[:220]}"); return
        back2, _ = reg.translate_response(resp2.json(), source=WireFormat.OPENAI_RESPONSES,
                                          target=WireFormat.ANTHROPIC_MESSAGES,
                                          client_search_tool=semantic2.client_search_tool)
        blocks2 = [f"{b.get('type')}:{b.get('name')}" if b.get("type") == "tool_use" else str(b.get("type"))
                   for b in back2.get("content", [])]
        print(f"[turn2 200] client would see: {' | '.join(blocks2)}  stop_reason={back2.get('stop_reason')}")

asyncio.run(run())
